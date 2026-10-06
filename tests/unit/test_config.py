from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from bcb_pipeline.config import ConfigError, Faixa, SerieConfig, load_series

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config" / "series.yaml"


def _write(tmp_path: Path, conteudo: str) -> Path:
    path = tmp_path / "series.yaml"
    path.write_text(conteudo, encoding="utf-8")
    return path


def test_repository_config_has_the_five_initial_series() -> None:
    series = load_series(REPO_CONFIG)

    assert sorted(s.codigo for s in series) == [1, 11, 12, 432, 433]
    assert all(s.faixa is not None for s in series)


def test_faixa_is_parsed_as_exact_decimal(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "carga_inicial: 2000-01-01\nseries:\n"
        "  - {codigo: 1, nome: a, periodicidade: diaria, unidade: x, faixa: {min: 0, max: 0.15}}",
    )

    (serie,) = load_series(path)

    assert serie.faixa == Faixa(Decimal("0"), Decimal("0.15"))


def test_variacao_max_pct_is_optional_and_exact(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "carga_inicial: 2000-01-01\nseries:\n"
        "  - {codigo: 1, nome: a, periodicidade: diaria, unidade: x, variacao_max_pct: 7.5}\n"
        "  - {codigo: 2, nome: b, periodicidade: diaria, unidade: x}",
    )

    com, sem = load_series(path)

    assert com.variacao_max_pct == Decimal("7.5")
    assert sem.variacao_max_pct is None


def test_serie_inherits_carga_inicial_unless_overridden(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
carga_inicial: 2000-01-01
series:
  - {codigo: 1, nome: a, periodicidade: diaria, unidade: x}
  - {codigo: 2, nome: b, periodicidade: mensal, unidade: x, inicio: 2015-06-01}
""",
    )

    a, b = load_series(path)

    assert a.inicio == date(2000, 1, 1)
    assert b.inicio == date(2015, 6, 1)


@pytest.mark.parametrize(
    ("conteudo", "erro"),
    [
        ("series: []", "carga_inicial"),
        ("carga_inicial: 2000-01-01\nseries: []", "nenhuma série"),
        (
            "carga_inicial: 2000-01-01\nseries:\n"
            "  - {codigo: 1, nome: a, periodicidade: anual, unidade: x}",
            "periodicidade",
        ),
        (
            "carga_inicial: 2000-01-01\nseries:\n"
            "  - {codigo: 1, nome: a, periodicidade: diaria, unidade: x}\n"
            "  - {codigo: 1, nome: b, periodicidade: diaria, unidade: x}",
            "repetido",
        ),
        ("carga_inicial: 2000-01-01\nseries:\n  - {codigo: 1}", "sem os campos"),
        (
            "carga_inicial: 2000-01-01\nseries:\n"
            "  - {codigo: 1, nome: a, periodicidade: diaria, unidade: x, faixa: {min: 5, max: 1}}",
            "min deve ser menor",
        ),
        (
            "carga_inicial: 2000-01-01\nseries:\n"
            "  - {codigo: 1, nome: a, periodicidade: diaria, unidade: x, faixa: [1, 2]}",
            "faixa",
        ),
        (
            "carga_inicial: 2000-01-01\nseries:\n"
            "  - {codigo: 1, nome: a, periodicidade: diaria, unidade: x, variacao_max_pct: 0}",
            "maior que zero",
        ),
        (
            "carga_inicial: 2000-01-01\nseries:\n"
            "  - {codigo: 1, nome: a, periodicidade: diaria, unidade: x, variacao_max_pct: abc}",
            "deve ser um número",
        ),
    ],
)
def test_invalid_config_is_rejected(tmp_path: Path, conteudo: str, erro: str) -> None:
    with pytest.raises(ConfigError, match=erro):
        load_series(_write(tmp_path, conteudo))


@pytest.mark.parametrize(
    ("faixa", "variacao"),
    [(None, None), (Faixa(Decimal("0"), Decimal("0.15")), Decimal("10"))],
)
def test_serie_round_trips_through_xcom_dict(faixa: Faixa | None, variacao: Decimal | None) -> None:
    serie = SerieConfig(11, "Selic", "diaria", "% a.d.", date(2000, 1, 1), faixa, variacao)

    assert SerieConfig.from_dict(serie.to_dict()) == serie
