from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise

import pytest

from bcb_pipeline.transform import (
    Observacao,
    ParseError,
    deduplicar,
    janelas,
    parse_data,
    parse_payload,
    parse_valor,
)


def test_parse_data_brazilian_format() -> None:
    assert parse_data("29/02/2024") == date(2024, 2, 29)


@pytest.mark.parametrize("texto", ["2024-01-02", "1/2/2024", "31/02/2024", ""])
def test_parse_data_rejects_invalid(texto: str) -> None:
    with pytest.raises(ParseError):
        parse_data(texto)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("0.043739", Decimal("0.043739")),  # formato do JSON
        ("5,2204", Decimal("5.2204")),  # formato do CSV
        ("1.234,56", Decimal("1234.56")),  # vírgula decimal com milhar
        (" -0.10 ", Decimal("-0.10")),
    ],
)
def test_parse_valor_accepts_dot_and_comma(texto: str, esperado: Decimal) -> None:
    assert parse_valor(texto) == esperado


@pytest.mark.parametrize("texto", ["abc", "NaN", "Infinity", ""])
def test_parse_valor_rejects_invalid(texto: str) -> None:
    with pytest.raises(ParseError):
        parse_valor(texto)


def test_parse_payload_keeps_valid_and_reports_discarded() -> None:
    payload = [
        {"data": "02/01/2024", "valor": "0.043739"},
        {"data": "03/01/2024", "valor": ""},
        {"data": "lixo", "valor": "1"},
        {"valor": "1"},
    ]

    result = parse_payload(payload)

    assert result.observacoes == [Observacao(date(2024, 1, 2), Decimal("0.043739"))]
    assert len(result.descartados) == 3


def test_deduplicar_keeps_last_and_sorts() -> None:
    obs = [
        Observacao(date(2024, 1, 3), Decimal("1")),
        Observacao(date(2024, 1, 2), Decimal("1")),
        Observacao(date(2024, 1, 3), Decimal("2")),  # revisão posterior
    ]

    assert deduplicar(obs) == [
        Observacao(date(2024, 1, 2), Decimal("1")),
        Observacao(date(2024, 1, 3), Decimal("2")),
    ]


def test_janelas_are_contiguous_and_bounded() -> None:
    resultado = janelas(date(2000, 1, 1), date(2026, 9, 30), anos=10)

    assert resultado[0][0] == date(2000, 1, 1)
    assert resultado[-1][1] == date(2026, 9, 30)
    for (_, fim), (proximo_inicio, _) in pairwise(resultado):
        assert proximo_inicio == fim + timedelta(days=1)
    for inicio, fim in resultado:
        assert fim < inicio.replace(year=inicio.year + 10)


def test_janelas_short_range_is_single_window() -> None:
    assert janelas(date(2026, 9, 29), date(2026, 9, 30), anos=10) == [
        (date(2026, 9, 29), date(2026, 9, 30))
    ]


def test_janelas_leap_day_start() -> None:
    assert janelas(date(2024, 2, 29), date(2026, 1, 1), anos=1)[0] == (
        date(2024, 2, 29),
        date(2025, 2, 27),
    )


def test_janelas_empty_when_start_after_end() -> None:
    assert janelas(date(2026, 1, 2), date(2026, 1, 1), anos=10) == []
