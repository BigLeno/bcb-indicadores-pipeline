"""Escrita nas camadas raw e staging do warehouse. Todas as operações são idempotentes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from bcb_pipeline.config import SerieConfig
from bcb_pipeline.transform import Observacao


@dataclass(frozen=True)
class UpsertResult:
    """Contagem do upsert no staging."""

    inseridas: int
    atualizadas: int
    inalteradas: int


def payload_sha256(registros: list[dict[str, Any]]) -> str:
    """Hash estável do payload (independe da ordem das chaves)."""
    canonico = json.dumps(registros, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonico.encode()).hexdigest()


def sincronizar_catalogo(conn: psycopg.Connection, series: Sequence[SerieConfig]) -> None:
    """Garante uma linha em `staging.serie` por série configurada, com os dados do YAML."""
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO staging.serie (serie_id, nome, periodicidade, unidade)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (serie_id) DO UPDATE
               SET nome = EXCLUDED.nome,
                   periodicidade = EXCLUDED.periodicidade,
                   unidade = EXCLUDED.unidade,
                   atualizado_em = now()
             WHERE (serie.nome, serie.periodicidade, serie.unidade)
                   IS DISTINCT FROM (EXCLUDED.nome, EXCLUDED.periodicidade, EXCLUDED.unidade)
            """,
            [(s.codigo, s.nome, s.periodicidade, s.unidade) for s in series],
        )


def ultima_data(conn: psycopg.Connection, serie_id: int) -> date | None:
    """Data mais recente já carregada no staging para a série."""
    row = conn.execute(
        "SELECT max(data) FROM staging.serie_valor WHERE serie_id = %s", (serie_id,)
    ).fetchone()
    return row[0] if row else None


def inserir_raw(
    conn: psycopg.Connection,
    serie_id: int,
    inicio: date,
    fim: date,
    registros: list[dict[str, Any]],
    run_id: str | None,
) -> tuple[int, bool]:
    """Grava a resposta em `raw.sgs_payload`. Devolve (id, se a linha é nova).

    A mesma resposta para a mesma janela não é gravada de novo: devolve o id existente.
    """
    sha = payload_sha256(registros)
    row = conn.execute(
        """
        INSERT INTO raw.sgs_payload
               (serie_id, janela_inicio, janela_fim, payload, payload_sha256, qtd_registros, run_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT ON CONSTRAINT sgs_payload_resposta_unica DO NOTHING
        RETURNING id
        """,
        (serie_id, inicio, fim, Jsonb(registros), sha, len(registros), run_id),
    ).fetchone()
    if row is not None:
        return row[0], True

    existente = conn.execute(
        """
        SELECT id FROM raw.sgs_payload
         WHERE serie_id = %s AND janela_inicio = %s AND janela_fim = %s AND payload_sha256 = %s
        """,
        (serie_id, inicio, fim, sha),
    ).fetchone()
    if existente is None:  # pragma: no cover - só com remoção concorrente
        raise RuntimeError(f"payload em conflito não encontrado (série {serie_id})")
    return existente[0], False


def ler_raw(conn: psycopg.Connection, raw_ids: Sequence[int]) -> list[list[dict[str, Any]]]:
    """Payloads das linhas de raw pedidas, em ordem de ingestão (id crescente)."""
    rows = conn.execute(
        "SELECT payload FROM raw.sgs_payload WHERE id = ANY(%s) ORDER BY id", (list(raw_ids),)
    ).fetchall()
    return [row[0] for row in rows]


def upsert_staging(
    conn: psycopg.Connection, serie_id: int, observacoes: Sequence[Observacao]
) -> UpsertResult:
    """Upsert em `staging.serie_valor` pela PK (serie_id, data).

    Linha existente só é reescrita se o valor mudou, então `atualizado_em` marca
    revisões reais do BCB. `observacoes` não pode ter datas repetidas.
    """
    if not observacoes:
        return UpsertResult(0, 0, 0)
    rows = conn.execute(
        """
        INSERT INTO staging.serie_valor AS sv (serie_id, data, valor)
        SELECT %s, t.data, t.valor
          FROM unnest(%s::date[], %s::numeric[]) AS t(data, valor)
        ON CONFLICT (serie_id, data) DO UPDATE
           SET valor = EXCLUDED.valor,
               atualizado_em = now()
         WHERE sv.valor IS DISTINCT FROM EXCLUDED.valor
        RETURNING (xmax = 0) AS inserida
        """,
        (serie_id, [o.data for o in observacoes], [o.valor for o in observacoes]),
    ).fetchall()
    # xmax = 0 identifica linha recém-inserida; as demais retornadas foram atualizadas.
    # Linhas com valor igual não passam no WHERE e não voltam no RETURNING.
    inseridas = sum(1 for (inserida,) in rows if inserida)
    atualizadas = len(rows) - inseridas
    return UpsertResult(inseridas, atualizadas, len(observacoes) - len(rows))
