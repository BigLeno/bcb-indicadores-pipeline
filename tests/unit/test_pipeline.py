from datetime import date

from bcb_pipeline.config import SerieConfig
from bcb_pipeline.pipeline import janela_de_carga

SERIE = SerieConfig(11, "Selic", "diaria", "% a.d.", inicio=date(2000, 1, 1))
HOJE = date(2026, 9, 30)


def test_first_run_does_historical_load_from_configured_start() -> None:
    assert janela_de_carga(SERIE, None, HOJE) == (date(2000, 1, 1), HOJE)


def test_incremental_starts_at_last_loaded_date_inclusive() -> None:
    assert janela_de_carga(SERIE, date(2026, 9, 26), HOJE) == (date(2026, 9, 26), HOJE)


def test_nothing_to_fetch_when_already_up_to_date_in_the_future() -> None:
    assert janela_de_carga(SERIE, date(2026, 10, 1), HOJE) is None


def test_backfill_ignores_what_was_already_loaded() -> None:
    intervalo = (date(2024, 1, 1), date(2024, 1, 2))

    assert janela_de_carga(SERIE, date(2026, 9, 29), HOJE, backfill=intervalo) == intervalo
