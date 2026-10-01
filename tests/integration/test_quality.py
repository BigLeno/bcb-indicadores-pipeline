from datetime import date
from decimal import Decimal

import psycopg
import pytest

from bcb_pipeline import loader, quality
from bcb_pipeline.config import Faixa, SerieConfig
from bcb_pipeline.transform import Observacao

HOJE = date(2026, 9, 30)
SERIE = SerieConfig(
    1, "Dólar", "diaria", "R$/US$", date(2000, 1, 1), Faixa(Decimal(1), Decimal(10))
)


def _carregar(conn: psycopg.Connection, *pares: tuple[str, str]) -> None:
    loader.sincronizar_catalogo(conn, [SERIE])
    obs = [Observacao(date.fromisoformat(d), Decimal(v)) for d, v in pares]
    loader.upsert_staging(conn, SERIE.codigo, obs)


def _violacoes(conn: psycopg.Connection, serie: SerieConfig = SERIE) -> dict[str, int]:
    return {r.nome: r.violacoes for r in quality.executar_checagens(conn, serie, HOJE)}


def test_clean_series_passes_every_check(conn: psycopg.Connection) -> None:
    _carregar(conn, ("2026-09-29", "5.2204"), ("2026-09-30", "5.1809"))

    resultados = quality.executar_checagens(conn, SERIE, HOJE)

    assert {r.nome for r in resultados} == {
        "serie_sem_dados",
        "valores_nulos",
        "datas_futuras",
        "datas_duplicadas",
        "fora_da_faixa",
    }
    quality.exigir_aprovacao(SERIE, resultados)


def test_empty_series_fails(conn: psycopg.Connection) -> None:
    loader.sincronizar_catalogo(conn, [SERIE])

    assert _violacoes(conn)["serie_sem_dados"] == 1


def test_future_date_fails(conn: psycopg.Connection) -> None:
    _carregar(conn, ("2026-09-30", "5.18"), ("2026-10-01", "5.19"))

    assert _violacoes(conn)["datas_futuras"] == 1


def test_value_out_of_range_fails_with_sample(conn: psycopg.Connection) -> None:
    _carregar(conn, ("2026-09-29", "0.52"), ("2026-09-30", "51.80"), ("2026-09-28", "5.2"))

    resultado = next(
        r for r in quality.executar_checagens(conn, SERIE, HOJE) if r.nome == "fora_da_faixa"
    )

    assert resultado.violacoes == 2
    with pytest.raises(quality.QualityCheckError, match="fora_da_faixa: 2"):
        quality.exigir_aprovacao(SERIE, [resultado])


def test_range_check_is_skipped_without_faixa(conn: psycopg.Connection) -> None:
    sem_faixa = SerieConfig(1, "Dólar", "diaria", "R$/US$", date(2000, 1, 1))
    _carregar(conn, ("2026-09-30", "999"))

    assert "fora_da_faixa" not in _violacoes(conn, sem_faixa)
