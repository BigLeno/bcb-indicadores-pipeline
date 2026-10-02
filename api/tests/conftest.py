"""O banco de teste do Django recebe o schema real do pipeline (sql/migrations).

Como os models são `managed = False`, o Django não cria as tabelas. Depois que o
pytest-django cria o banco `test_<nome>`, aplicamos aqui as mesmas migrations SQL
que o pipeline usa, então os testes rodam contra os marts de verdade.
"""

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from django.core.cache import cache
from django.db import connection
from rest_framework.test import APIClient

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "sql" / "migrations"
MARTS = ("ipca_mensal", "cdi_mensal", "dolar_diario", "dolar_mensal")
SERIES = {
    1: ("Dólar comercial (venda)", "diaria", "R$/US$"),
    11: ("Taxa Selic diária", "diaria", "% a.d."),
    12: ("Taxa CDI diária", "diaria", "% a.d."),
    433: ("IPCA - variação mensal", "mensal", "% a.m."),
}


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup: None, django_db_blocker: Any) -> None:
    arquivos = sorted(MIGRATIONS_DIR.glob("*.sql"))
    assert arquivos, f"nenhuma migration em {MIGRATIONS_DIR}"
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        for arquivo in arquivos:
            cursor.execute(arquivo.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _sem_throttling_entre_testes() -> None:
    """O contador do throttling fica no cache; zerar evita 429 por acúmulo entre testes."""
    cache.clear()


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def carregar(db: None) -> Callable[[int, list[tuple[date, str]]], None]:
    """Insere observações no staging e atualiza os marts, como o pipeline faria."""

    def _carregar(serie_id: int, pontos: list[tuple[date, str]]) -> None:
        nome, periodicidade, unidade = SERIES[serie_id]
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO staging.serie (serie_id, nome, periodicidade, unidade)"
                " VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                [serie_id, nome, periodicidade, unidade],
            )
            for data, valor in pontos:
                cursor.execute(
                    "INSERT INTO staging.serie_valor (serie_id, data, valor) VALUES (%s, %s, %s)",
                    [serie_id, data, Decimal(valor)],
                )
            for mart in MARTS:
                cursor.execute(f"REFRESH MATERIALIZED VIEW marts.{mart}")

    return _carregar
