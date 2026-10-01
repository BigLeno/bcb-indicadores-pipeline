"""Etapas do pipeline, independentes do Airflow. A DAG só chama estas funções."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import structlog

from bcb_pipeline import loader, marts, quality
from bcb_pipeline.config import SerieConfig, load_series
from bcb_pipeline.settings import WarehouseSettings
from bcb_pipeline.sgs_client import SgsClient
from bcb_pipeline.transform import deduplicar, parse_payload

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ResultadoExtracao:
    """O que a extração de uma série gravou no raw (vai por XCom para o staging)."""

    serie_id: int
    janela_inicio: str | None
    janela_fim: str | None
    janelas: int
    registros_lidos: int
    payloads_novos: int
    raw_ids: list[int]


def _conectar() -> psycopg.Connection:
    return psycopg.connect(WarehouseSettings.from_env().conninfo)


def janela_de_carga(
    serie: SerieConfig,
    ultima_carregada: date | None,
    fim: date,
    backfill: tuple[date, date] | None = None,
) -> tuple[date, date] | None:
    """Intervalo [inicio, fim] a buscar, ou None se não há nada a buscar.

    - backfill: exatamente o intervalo pedido, independente do que já foi carregado;
    - incremental: da última data carregada (inclusive, para pegar revisões do último
      ponto) até `fim`; sem dados ainda, parte do `inicio` configurado (carga histórica).
    """
    if backfill is not None:
        inicio, fim = backfill
    else:
        inicio = ultima_carregada or serie.inicio
    return (inicio, fim) if inicio <= fim else None


def preparar_series(config_path: Path | None = None) -> list[dict[str, Any]]:
    """Lê o YAML, sincroniza `staging.serie` e devolve as séries serializadas para o mapping."""
    series = load_series(config_path)
    with _conectar() as conn:
        loader.sincronizar_catalogo(conn, series)
    logger.info("catalogo_sincronizado", series=[s.codigo for s in series])
    return [s.to_dict() for s in series]


def extrair_serie(
    serie: SerieConfig,
    fim: date,
    run_id: str | None = None,
    backfill: tuple[date, date] | None = None,
    client: SgsClient | None = None,
) -> ResultadoExtracao:
    """Busca a série na API e grava cada janela em `raw.sgs_payload`."""
    log = logger.bind(serie_id=serie.codigo, run_id=run_id)
    with _conectar() as conn:
        janela = janela_de_carga(serie, loader.ultima_data(conn, serie.codigo), fim, backfill)
        if janela is None:
            log.info("extracao_sem_janela", fim=fim.isoformat())
            return ResultadoExtracao(serie.codigo, None, None, 0, 0, 0, [])

        raw_ids: list[int] = []
        registros_lidos = payloads_novos = 0
        with client or SgsClient.from_settings() as sgs:
            for resposta in sgs.fetch_range(serie.codigo, *janela):
                raw_id, novo = loader.inserir_raw(
                    conn, serie.codigo, resposta.inicio, resposta.fim, resposta.registros, run_id
                )
                conn.commit()  # cada janela gravada sobrevive a uma falha nas seguintes
                raw_ids.append(raw_id)
                registros_lidos += len(resposta.registros)
                payloads_novos += int(novo)

    resultado = ResultadoExtracao(
        serie_id=serie.codigo,
        janela_inicio=janela[0].isoformat(),
        janela_fim=janela[1].isoformat(),
        janelas=len(raw_ids),
        registros_lidos=registros_lidos,
        payloads_novos=payloads_novos,
        raw_ids=raw_ids,
    )
    log.info("extracao_concluida", **{k: v for k, v in asdict(resultado).items() if k != "raw_ids"})
    return resultado


def carregar_staging(serie_id: int, raw_ids: Sequence[int]) -> dict[str, int]:
    """Lê os payloads do raw, converte e faz upsert em `staging.serie_valor`."""
    log = logger.bind(serie_id=serie_id)
    with _conectar() as conn:
        payloads = loader.ler_raw(conn, raw_ids)
        observacoes, descartados = [], []
        for payload in payloads:
            parsed = parse_payload(payload)
            observacoes.extend(parsed.observacoes)
            descartados.extend(parsed.descartados)
        unicas = deduplicar(observacoes)
        resultado = loader.upsert_staging(conn, serie_id, unicas)

    for registro, motivo in descartados[:10]:
        log.warning("registro_descartado", registro=registro, motivo=motivo)
    stats = {
        "serie_id": serie_id,
        "lidas": len(observacoes),
        "descartadas": len(descartados),
        "duplicadas": len(observacoes) - len(unicas),
        "inseridas": resultado.inseridas,
        "atualizadas": resultado.atualizadas,
        "inalteradas": resultado.inalteradas,
    }
    log.info("staging_carregado", **stats)
    return stats


def checar_qualidade(serie: SerieConfig, hoje: date) -> dict[str, int]:
    """Roda as checagens da série no staging; falha com `QualityCheckError` se houver violação."""
    with _conectar() as conn:
        resultados = quality.executar_checagens(conn, serie, hoje)
    violacoes = {r.nome: r.violacoes for r in resultados}
    logger.info(
        "qualidade_verificada",
        serie_id=serie.codigo,
        aprovada=all(r.ok for r in resultados),
        violacoes=violacoes,
    )
    quality.exigir_aprovacao(serie, resultados)
    return violacoes


def atualizar_marts() -> dict[str, int]:
    """Refresh de todos os marts; devolve a quantidade de linhas de cada um."""
    with _conectar() as conn:
        linhas = marts.atualizar(conn)
    logger.info("marts_atualizados", linhas=linhas)
    return linhas
