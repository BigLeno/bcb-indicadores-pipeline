from pathlib import Path

import psycopg
import pytest

from bcb_pipeline import migrate

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "sql" / "migrations"


def test_all_migrations_are_recorded(conn: psycopg.Connection) -> None:
    versoes = [
        r[0] for r in conn.execute("SELECT version FROM public.schema_migrations ORDER BY 1")
    ]

    assert versoes == [m.version for m in migrate.discover(MIGRATIONS_DIR)]


def test_reapplying_is_a_noop(conn: psycopg.Connection) -> None:
    assert migrate.apply(conn, migrate.discover(MIGRATIONS_DIR)) == []


def test_edited_migration_is_rejected(conn: psycopg.Connection) -> None:
    editada = migrate.discover(MIGRATIONS_DIR)
    editada[0] = migrate.Migration(editada[0].version, editada[0].name, "SELECT 'editada';")

    with pytest.raises(migrate.MigrationError, match="editada depois de aplicada"):
        migrate.apply(conn, editada)


def test_layers_exist(conn: psycopg.Connection) -> None:
    objetos = {
        f"{schema}.{nome}"
        for schema, nome in conn.execute(
            """
            SELECT n.nspname, c.relname FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname IN ('raw', 'staging', 'marts') AND c.relkind IN ('r', 'm')
            """
        )
    }

    assert objetos == {
        "raw.sgs_payload",
        "staging.serie",
        "staging.serie_valor",
        "marts.ipca_mensal",
        "marts.cdi_mensal",
        "marts.dolar_diario",
        "marts.dolar_mensal",
    }
