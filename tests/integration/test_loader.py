from datetime import date
from decimal import Decimal

import psycopg

from bcb_pipeline import loader
from bcb_pipeline.config import SerieConfig
from bcb_pipeline.transform import Observacao

SERIE = SerieConfig(11, "Selic", "diaria", "% a.d.", date(2000, 1, 1))
PAYLOAD = [{"data": "02/01/2024", "valor": "0.043739"}]


def _obs(*pares: tuple[str, str]) -> list[Observacao]:
    return [Observacao(date.fromisoformat(d), Decimal(v)) for d, v in pares]


def test_catalog_sync_is_idempotent_and_updates_names(conn: psycopg.Connection) -> None:
    loader.sincronizar_catalogo(conn, [SERIE])
    loader.sincronizar_catalogo(conn, [SERIE])
    renomeada = SerieConfig(11, "Selic renomeada", "diaria", "% a.d.", date(2000, 1, 1))
    loader.sincronizar_catalogo(conn, [renomeada])

    assert conn.execute("SELECT serie_id, nome FROM staging.serie").fetchall() == [
        (11, "Selic renomeada")
    ]


def test_same_raw_payload_is_stored_once(conn: psycopg.Connection) -> None:
    janela = (date(2024, 1, 1), date(2024, 1, 31))

    primeiro = loader.inserir_raw(conn, 11, *janela, PAYLOAD, "run-1")
    repetido = loader.inserir_raw(conn, 11, *janela, PAYLOAD, "run-2")
    revisado = loader.inserir_raw(conn, 11, *janela, [{**PAYLOAD[0], "valor": "1"}], "run-3")

    assert primeiro[1] is True
    assert repetido == (primeiro[0], False)
    assert revisado[1] is True
    assert revisado[0] != primeiro[0]
    assert conn.execute("SELECT count(*) FROM raw.sgs_payload").fetchone() == (2,)
    assert loader.ler_raw(conn, [primeiro[0], revisado[0]]) == [
        PAYLOAD,
        [{**PAYLOAD[0], "valor": "1"}],
    ]


def test_upsert_counts_inserted_updated_and_unchanged(conn: psycopg.Connection) -> None:
    loader.sincronizar_catalogo(conn, [SERIE])
    base = _obs(("2024-01-02", "0.04"), ("2024-01-03", "0.04"), ("2024-01-04", "0.04"))

    assert loader.upsert_staging(conn, 11, base) == loader.UpsertResult(3, 0, 0)
    assert loader.upsert_staging(conn, 11, base) == loader.UpsertResult(0, 0, 3)

    revisao = _obs(("2024-01-04", "0.05"), ("2024-01-05", "0.04"))
    assert loader.upsert_staging(conn, 11, revisao) == loader.UpsertResult(1, 1, 0)

    assert conn.execute(
        "SELECT valor FROM staging.serie_valor WHERE data = '2024-01-04'"
    ).fetchone() == (Decimal("0.05"),)
    assert loader.ultima_data(conn, 11) == date(2024, 1, 5)


def test_numeric_keeps_exact_value(conn: psycopg.Connection) -> None:
    loader.sincronizar_catalogo(conn, [SERIE])
    loader.upsert_staging(conn, 11, _obs(("2024-01-02", "0.043739")))

    assert conn.execute("SELECT valor FROM staging.serie_valor").fetchone() == (
        Decimal("0.043739"),
    )


def test_ultima_data_is_none_for_empty_series(conn: psycopg.Connection) -> None:
    assert loader.ultima_data(conn, 11) is None
