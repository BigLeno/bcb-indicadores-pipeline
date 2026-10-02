"""Usuário de login da API, com a senha vinda do ambiente.

A migration 005 cria o papel `api_leitura` (sem login e sem senha). Aqui se cria, ou
atualiza, o usuário que a API usa para conectar, como membro desse papel.
"""

from __future__ import annotations

import psycopg
from psycopg import sql

PAPEL_LEITURA = "api_leitura"


def garantir_usuario_leitura(conn: psycopg.Connection, usuario: str, senha: str) -> bool:
    """Cria ou atualiza o usuário. Devolve True se ele foi criado agora."""
    papel = sql.Identifier(usuario)
    with conn.transaction():
        existe = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (usuario,)).fetchone()
        acao = (
            "ALTER ROLE {} WITH LOGIN PASSWORD {}" if existe else "CREATE ROLE {} LOGIN PASSWORD {}"
        )
        conn.execute(sql.SQL(acao).format(papel, sql.Literal(senha)))
        conn.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(PAPEL_LEITURA), papel))
        # Defesa em profundidade: mesmo que um GRANT de escrita escape, as sessões
        # desse usuário são só de leitura.
        conn.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(papel))
    return existe is None
