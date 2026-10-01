"""Fixtures dos testes de integração: um banco Postgres descartável por sessão.

Conecta com as credenciais `WAREHOUSE_*` (precisam de permissão de CREATE DATABASE),
cria `bcb_test_<aleatório>`, aplica as migrations reais e apaga o banco no fim.
O banco do warehouse em si nunca é tocado.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from bcb_pipeline import migrate
from bcb_pipeline.settings import MissingSettingError, WarehouseSettings

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "sql" / "migrations"
INTEGRATION_DIR = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Marca como `integration` todo teste desta pasta (permite `-m "not integration"`)."""
    for item in items:
        if INTEGRATION_DIR in Path(item.fspath).parents:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def test_db() -> Iterator[WarehouseSettings]:
    """Cria o banco de teste com as migrations aplicadas."""
    try:
        admin = WarehouseSettings.from_env()
    except MissingSettingError as exc:
        # Falhar (e não pular): no CI, um teste de integração pulado em silêncio daria
        # um verde falso. Para rodar só os unitários: pytest -m "not integration".
        pytest.fail(f"testes de integração precisam de um Postgres: {exc}")

    nome = f"bcb_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin.conninfo, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    settings = replace(admin, dbname=nome)
    try:
        with psycopg.connect(settings.conninfo) as conn:
            migrate.apply(conn, migrate.discover(MIGRATIONS_DIR))
        yield settings
    finally:
        with psycopg.connect(admin.conninfo, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome))
            )


@pytest.fixture
def conn(test_db: WarehouseSettings) -> Iterator[psycopg.Connection]:
    """Conexão com o banco de teste, limpo antes de cada teste."""
    with psycopg.connect(test_db.conninfo) as connection:
        connection.execute("TRUNCATE raw.sgs_payload, staging.serie_valor, staging.serie CASCADE")
        connection.commit()
        yield connection


@pytest.fixture
def warehouse_env(test_db: WarehouseSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aponta as funções que leem `WAREHOUSE_*` do ambiente para o banco de teste."""
    monkeypatch.setenv("WAREHOUSE_DB", test_db.dbname)
