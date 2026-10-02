from django.db import models
from rest_framework import serializers

from indicadores.models import CdiMensal, DolarDiario, DolarMensal, IpcaMensal, Serie, SerieValor


class DecimalExato(serializers.DecimalField):
    """Decimal sem arredondar: devolve, como string, exatamente o valor do banco."""

    def __init__(self, **kwargs: object) -> None:
        kwargs.pop("max_digits", None)
        kwargs.pop("decimal_places", None)
        super().__init__(max_digits=None, decimal_places=None, **kwargs)


class LeituraSerializer(serializers.ModelSerializer):
    """Base: todo DecimalField do model vira DecimalExato."""

    serializer_field_mapping = {
        **serializers.ModelSerializer.serializer_field_mapping,
        models.DecimalField: DecimalExato,
    }


class SerieSerializer(LeituraSerializer):
    class Meta:
        model = Serie
        fields = ["serie_id", "nome", "periodicidade", "unidade", "atualizado_em"]


class SerieValorSerializer(LeituraSerializer):
    serie_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = SerieValor
        fields = ["serie_id", "data", "valor"]


class IpcaMensalSerializer(LeituraSerializer):
    class Meta:
        model = IpcaMensal
        fields = "__all__"


class CdiMensalSerializer(LeituraSerializer):
    class Meta:
        model = CdiMensal
        fields = "__all__"


class DolarDiarioSerializer(LeituraSerializer):
    class Meta:
        model = DolarDiario
        fields = "__all__"


class DolarMensalSerializer(LeituraSerializer):
    class Meta:
        model = DolarMensal
        fields = "__all__"
