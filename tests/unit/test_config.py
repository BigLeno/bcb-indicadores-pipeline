from datetime import date
from pathlib import Path

import pytest

from bcb_pipeline.config import ConfigError, SerieConfig, load_series

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config" / "series.yaml"


def _write(tmp_path: Path, conteudo: str) -> Path:
    path = tmp_path / "series.yaml"
    path.write_text(conteudo, encoding="utf-8")
    return path


def test_repository_config_has_the_five_initial_series() -> None:
    series = load_series(REPO_CONFIG)

    assert sorted(s.codigo for s in series) == [1, 11, 12, 432, 433]


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
    ],
)
def test_invalid_config_is_rejected(tmp_path: Path, conteudo: str, erro: str) -> None:
    with pytest.raises(ConfigError, match=erro):
        load_series(_write(tmp_path, conteudo))


def test_serie_round_trips_through_xcom_dict() -> None:
    serie = SerieConfig(11, "Selic", "diaria", "% a.d.", date(2000, 1, 1))

    assert SerieConfig.from_dict(serie.to_dict()) == serie
