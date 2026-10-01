"""Atualização dos marts (materialized views definidas em sql/migrations/004)."""

from __future__ import annotations

import psycopg
from psycopg import sql

MARTS: tuple[str, ...] = ("ipca_mensal", "cdi_mensal", "dolar_diario", "dolar_mensal")


def atualizar(conn: psycopg.Connection) -> dict[str, int]:
    """Faz o refresh de todos os marts numa transação e devolve as linhas de cada um.

    CONCURRENTLY: quem estiver lendo continua vendo a versão anterior até o commit,
    sem bloqueio. Exige o índice único que cada mart tem.
    """
    linhas: dict[str, int] = {}
    with conn.transaction():
        for nome in MARTS:
            mart = sql.Identifier("marts", nome)
            conn.execute(sql.SQL("REFRESH MATERIALIZED VIEW CONCURRENTLY {}").format(mart))
            row = conn.execute(sql.SQL("SELECT count(*) FROM {}").format(mart)).fetchone()
            linhas[nome] = row[0] if row else 0
    return linhas
