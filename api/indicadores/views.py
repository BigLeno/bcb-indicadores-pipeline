from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from indicadores import filters
from indicadores.models import CdiMensal, DolarDiario, DolarMensal, IpcaMensal, Serie, SerieValor
from indicadores.serializers import (
    CdiMensalSerializer,
    DolarDiarioSerializer,
    DolarMensalSerializer,
    IpcaMensalSerializer,
    SerieSerializer,
    SerieValorSerializer,
)

# Datas nas URLs de detalhe dos marts: /api/marts/ipca-mensal/2024-12-01/
DATA_NA_URL = r"\d{4}-\d{2}-\d{2}"


class SerieViewSet(viewsets.ReadOnlyModelViewSet):
    """Catálogo das séries carregadas pelo pipeline."""

    queryset = Serie.objects.all()
    serializer_class = SerieSerializer
    filter_backends: list = []  # catálogo pequeno: sem filtro nem ordenação
    pagination_class = None


class SerieValorViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Observações de cada série, filtráveis por série e período."""

    queryset = SerieValor.objects.all()
    serializer_class = SerieValorSerializer
    filterset_class = filters.SerieValorFiltro
    ordering_fields = ["data"]


def _mart(modelo, serializer, campo: str, descricao: str) -> type[viewsets.ReadOnlyModelViewSet]:
    """ViewSet somente leitura de um mart, filtrável por período e ordenável pela data."""

    class Mart(viewsets.ReadOnlyModelViewSet):
        __doc__ = descricao
        queryset = modelo.objects.all()
        serializer_class = serializer
        filterset_class = filters.filtro_por_periodo(modelo, campo)
        ordering_fields = [campo]
        lookup_value_regex = DATA_NA_URL

    Mart.__name__ = f"{modelo.__name__}ViewSet"
    return Mart


IpcaMensalViewSet = _mart(
    IpcaMensal,
    IpcaMensalSerializer,
    "mes",
    "IPCA: variação mensal e acumulados no ano e em 12 meses.",
)
CdiMensalViewSet = _mart(CdiMensal, CdiMensalSerializer, "mes", "CDI acumulado em cada mês.")
DolarDiarioViewSet = _mart(
    DolarDiario, DolarDiarioSerializer, "data", "Dólar de venda e variação diária."
)
DolarMensalViewSet = _mart(
    DolarMensal, DolarMensalSerializer, "mes", "Dólar: fechamento e variação mensal."
)


class HealthView(APIView):
    """Saúde da API e da conexão com o banco (usada pelo healthcheck do container)."""

    throttle_classes: list = []

    @extend_schema(
        responses={
            200: inline_serializer("Health", {"status": serializers.CharField()}),
            503: inline_serializer("HealthErro", {"status": serializers.CharField()}),
        }
    )
    def get(self, request: Request) -> Response:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:  # qualquer falha de banco deixa o serviço indisponível
            return Response({"status": "banco indisponível"}, status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"status": "ok"})
