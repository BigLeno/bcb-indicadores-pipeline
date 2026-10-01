"""Marts calculados sobre dados sintéticos com resultado conhecido."""

from datetime import date, timedelta
from decimal import Decimal

import psycopg

from bcb_pipeline import loader, marts
from bcb_pipeline.config import SerieConfig
from bcb_pipeline.transform import Observacao

IPCA = SerieConfig(433, "IPCA", "mensal", "% a.m.", date(2000, 1, 1))
CDI = SerieConfig(12, "CDI", "diaria", "% a.d.", date(2000, 1, 1))
DOLAR = SerieConfig(1, "Dólar", "diaria", "R$/US$", date(2000, 1, 1))


def _carregar(conn: psycopg.Connection, serie: SerieConfig, pares: list[tuple[date, str]]) -> None:
    loader.sincronizar_catalogo(conn, [serie])
    loader.upsert_staging(conn, serie.codigo, [Observacao(d, Decimal(v)) for d, v in pares])
    conn.commit()


def _meses(inicio: date, n: int) -> list[date]:
    return [
        date(inicio.year + (inicio.month - 1 + i) // 12, (inicio.month - 1 + i) % 12 + 1, 1)
        for i in range(n)
    ]


def test_ipca_accumulates_compounded_in_year_and_12_months(conn: psycopg.Connection) -> None:
    # 14 meses de 1%: em 12 meses, 1,01^12 - 1 = 12,682503%.
    _carregar(conn, IPCA, [(m, "1") for m in _meses(date(2023, 1, 1), 14)])

    marts.atualizar(conn)
    linhas = {
        r[0]: r[1:]
        for r in conn.execute(
            "SELECT mes, acumulado_ano_pct, acumulado_12m_pct FROM marts.ipca_mensal"
        )
    }

    assert linhas[date(2023, 3, 1)] == (Decimal("3.030100"), None)  # sem 12 meses ainda
    assert linhas[date(2023, 12, 1)] == (Decimal("12.682503"), Decimal("12.682503"))
    assert linhas[date(2024, 2, 1)] == (Decimal("2.010000"), Decimal("12.682503"))


def test_ipca_12m_is_null_when_a_month_is_missing(conn: psycopg.Connection) -> None:
    meses = _meses(date(2023, 1, 1), 13)
    del meses[5]  # sem junho: a janela de dezembro tem 11 meses
    _carregar(conn, IPCA, [(m, "1") for m in meses])

    marts.atualizar(conn)

    assert conn.execute(
        "SELECT acumulado_12m_pct FROM marts.ipca_mensal WHERE mes = '2023-12-01'"
    ).fetchone() == (None,)


def test_cdi_accumulates_within_each_month(conn: psycopg.Connection) -> None:
    dias = [date(2024, 1, 2) + timedelta(days=i) for i in range(3)] + [date(2024, 2, 1)]
    _carregar(conn, CDI, [(d, "0.04") for d in dias])

    marts.atualizar(conn)

    assert conn.execute(
        "SELECT mes, dias_uteis, acumulado_mes_pct, ultima_data FROM marts.cdi_mensal ORDER BY mes"
    ).fetchall() == [
        # 1,0004^3 - 1 = 0,120048%
        (date(2024, 1, 1), 3, Decimal("0.120048"), date(2024, 1, 4)),
        (date(2024, 2, 1), 1, Decimal("0.040000"), date(2024, 2, 1)),
    ]


def test_dolar_daily_and_monthly_variation(conn: psycopg.Connection) -> None:
    _carregar(
        conn,
        DOLAR,
        [
            (date(2024, 1, 30), "4.00"),
            (date(2024, 1, 31), "5.00"),  # fechamento de janeiro
            (date(2024, 2, 1), "5.50"),
            (date(2024, 2, 29), "4.50"),  # fechamento de fevereiro
        ],
    )

    marts.atualizar(conn)

    diario = conn.execute(
        "SELECT data, variacao_diaria_pct FROM marts.dolar_diario ORDER BY data"
    ).fetchall()
    assert diario == [
        (date(2024, 1, 30), None),
        (date(2024, 1, 31), Decimal("25.000000")),
        (date(2024, 2, 1), Decimal("10.000000")),
        (date(2024, 2, 29), Decimal("-18.181818")),
    ]
    mensal = conn.execute(
        "SELECT mes, data_fechamento, cotacao_fechamento, variacao_mensal_pct"
        " FROM marts.dolar_mensal ORDER BY mes"
    ).fetchall()
    assert mensal == [
        (date(2024, 1, 1), date(2024, 1, 31), Decimal("5.00"), None),
        (date(2024, 2, 1), date(2024, 2, 29), Decimal("4.50"), Decimal("-10.000000")),
    ]


def test_refresh_returns_row_counts_and_is_repeatable(conn: psycopg.Connection) -> None:
    _carregar(conn, IPCA, [(m, "0.5") for m in _meses(date(2024, 1, 1), 3)])

    assert marts.atualizar(conn) == {
        "ipca_mensal": 3,
        "cdi_mensal": 0,
        "dolar_diario": 0,
        "dolar_mensal": 0,
    }
    assert marts.atualizar(conn)["ipca_mensal"] == 3
