"""Usuário da API: lê marts e catálogo, e não escreve nem enxerga o raw."""

import uuid
from collections.abc import Iterator
from dataclasses import replace

import psycopg
import pytest
from psycopg import errors, sql

from bcb_pipeline.acesso import garantir_usuario_leitura
from bcb_pipeline.settings import WarehouseSettings


@pytest.fixture
def usuario_api(test_db: WarehouseSettings) -> Iterator[WarehouseSettings]:
    """Cria um usuário de leitura com nome único e o remove no fim (papéis são do cluster)."""
    nome, senha = f"api_teste_{uuid.uuid4().hex[:8]}", uuid.uuid4().hex
    with psycopg.connect(test_db.conninfo) as conn:
        assert garantir_usuario_leitura(conn, nome, senha) is True
        assert garantir_usuario_leitura(conn, nome, senha) is False  # idempotente
    yield replace(test_db, user=nome, password=senha)
    with psycopg.connect(test_db.conninfo, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(nome)))


def test_api_user_reads_marts_and_catalog(usuario_api: WarehouseSettings) -> None:
    with psycopg.connect(usuario_api.conninfo) as conn:
        conn.execute("SELECT count(*) FROM marts.ipca_mensal").fetchone()
        conn.execute("SELECT count(*) FROM staging.serie_valor").fetchone()


@pytest.mark.parametrize(
    "comando",
    [
        "INSERT INTO staging.serie (serie_id, nome, periodicidade, unidade)"
        " VALUES (999, 'x', 'diaria', 'x')",
        "DELETE FROM staging.serie_valor",
    ],
)
def test_api_user_cannot_write(usuario_api: WarehouseSettings, comando: str) -> None:
    with (
        psycopg.connect(usuario_api.conninfo) as conn,
        pytest.raises(errors.ReadOnlySqlTransaction),
    ):
        conn.execute(comando)


def test_api_user_cannot_read_raw(usuario_api: WarehouseSettings) -> None:
    with (
        psycopg.connect(usuario_api.conninfo) as conn,
        pytest.raises(errors.InsufficientPrivilege),
    ):
        conn.execute("SELECT * FROM raw.sgs_payload")
