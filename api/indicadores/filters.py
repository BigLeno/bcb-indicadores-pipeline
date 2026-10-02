"""Filtros de período (`data_inicio`/`data_fim`, inclusivos) e de série."""

from django import forms
from django.db import models
from django_filters import rest_framework as filters

from indicadores.models import SerieValor

# Só ISO 8601. Com LANGUAGE_CODE pt-br o Django também aceitaria "31/12/2024", e uma
# API não deve depender do idioma do servidor para interpretar datas.
FORMATO_DATA = ["%Y-%m-%d"]


class PeriodoForm(forms.Form):
    """Rejeita período invertido com HTTP 400, em vez de devolver lista vazia."""

    def clean(self) -> dict:
        dados = super().clean()
        inicio, fim = dados.get("data_inicio"), dados.get("data_fim")
        if inicio and fim and inicio > fim:
            raise forms.ValidationError("data_inicio deve ser anterior ou igual a data_fim.")
        return dados


def filtro_por_periodo(modelo: type[models.Model], campo: str) -> type[filters.FilterSet]:
    """FilterSet com `data_inicio`/`data_fim` sobre o campo de data do modelo."""

    class Filtro(filters.FilterSet):
        data_inicio = filters.DateFilter(
            field_name=campo,
            lookup_expr="gte",
            input_formats=FORMATO_DATA,
            label=f"{campo} a partir de (AAAA-MM-DD)",
        )
        data_fim = filters.DateFilter(
            field_name=campo,
            lookup_expr="lte",
            input_formats=FORMATO_DATA,
            label=f"{campo} até (AAAA-MM-DD)",
        )

        class Meta:
            model = modelo
            fields: list[str] = []
            form = PeriodoForm

    Filtro.__name__ = f"{modelo.__name__}Filtro"
    return Filtro


class SerieValorFiltro(filtro_por_periodo(SerieValor, "data")):
    serie = filters.NumberFilter(field_name="serie_id", label="Código SGS da série")

    class Meta:
        model = SerieValor
        fields: list[str] = []
        form = PeriodoForm
