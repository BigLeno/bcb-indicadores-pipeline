"""Models somente leitura sobre as tabelas do pipeline.

`managed = False`: o schema pertence ao pipeline (sql/migrations); o Django nunca cria
nem altera essas tabelas. Os nomes não levam schema porque a conexão usa
`search_path=marts,staging`.

`max_digits`/`decimal_places` só satisfazem a validação do Django: as colunas são
`numeric` sem precisão fixa, e o serializer devolve o valor exato do banco.
"""

from django.db import models

DECIMAL = {"max_digits": 30, "decimal_places": 10}


class Serie(models.Model):
    """Catálogo das séries (staging.serie)."""

    serie_id = models.IntegerField(primary_key=True, help_text="Código da série no SGS.")
    nome = models.TextField()
    periodicidade = models.TextField(help_text="diaria ou mensal")
    unidade = models.TextField()
    atualizado_em = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "serie"
        ordering = ["serie_id"]


class SerieValor(models.Model):
    """Observações tipadas de cada série (staging.serie_valor)."""

    pk = models.CompositePrimaryKey("serie_id", "data")
    serie = models.ForeignKey(Serie, on_delete=models.DO_NOTHING, related_name="valores")
    data = models.DateField()
    valor = models.DecimalField(**DECIMAL)

    class Meta:
        managed = False
        db_table = "serie_valor"
        ordering = ["serie_id", "data"]


class IpcaMensal(models.Model):
    """marts.ipca_mensal"""

    mes = models.DateField(primary_key=True)
    variacao_mensal_pct = models.DecimalField(**DECIMAL)
    acumulado_ano_pct = models.DecimalField(**DECIMAL)
    acumulado_12m_pct = models.DecimalField(
        **DECIMAL, null=True, help_text="Nulo enquanto não há 12 meses consecutivos."
    )

    class Meta:
        managed = False
        db_table = "ipca_mensal"
        ordering = ["mes"]


class CdiMensal(models.Model):
    """marts.cdi_mensal"""

    mes = models.DateField(primary_key=True)
    dias_uteis = models.BigIntegerField()
    acumulado_mes_pct = models.DecimalField(**DECIMAL)
    ultima_data = models.DateField(help_text="No mês corrente, o acumulado vai até esta data.")

    class Meta:
        managed = False
        db_table = "cdi_mensal"
        ordering = ["mes"]


class DolarDiario(models.Model):
    """marts.dolar_diario"""

    data = models.DateField(primary_key=True)
    cotacao = models.DecimalField(**DECIMAL)
    cotacao_anterior = models.DecimalField(**DECIMAL, null=True)
    variacao_diaria_pct = models.DecimalField(**DECIMAL, null=True)

    class Meta:
        managed = False
        db_table = "dolar_diario"
        ordering = ["data"]


class DolarMensal(models.Model):
    """marts.dolar_mensal"""

    mes = models.DateField(primary_key=True)
    data_fechamento = models.DateField()
    cotacao_fechamento = models.DecimalField(**DECIMAL)
    variacao_mensal_pct = models.DecimalField(**DECIMAL, null=True)

    class Meta:
        managed = False
        db_table = "dolar_mensal"
        ordering = ["mes"]
