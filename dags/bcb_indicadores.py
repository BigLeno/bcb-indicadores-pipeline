"""Ingestão diária das séries SGS do BCB: API -> raw -> staging.

A DAG só orquestra; a lógica está em `bcb_pipeline.pipeline`.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from typing import Any

import pendulum
from airflow.sdk import dag, get_current_context, task

from bcb_pipeline import pipeline
from bcb_pipeline.config import SerieConfig

TZ = "America/Sao_Paulo"


def _data_local(momento: pendulum.DateTime | None) -> date:
    return (momento or pendulum.now(TZ)).in_timezone(TZ).date()


@dag(
    dag_id="bcb_indicadores",
    description="Séries do SGS/BCB: API -> raw -> staging",
    schedule="0 9 * * *",  # 09:00 de Brasília: a série do dia anterior já foi publicada
    start_date=pendulum.datetime(2026, 1, 1, tz=TZ),
    catchup=False,  # a carga histórica vem da lógica incremental, não de runs retroativos
    max_active_runs=1,
    default_args={
        "retries": 3,
        "retry_delay": timedelta(minutes=1),
        "retry_exponential_backoff": True,
        "max_retry_delay": timedelta(minutes=15),
        "execution_timeout": timedelta(minutes=30),
    },
    tags=["bcb", "sgs"],
)
def bcb_indicadores() -> None:
    @task
    def preparar_series() -> list[dict[str, Any]]:
        """Lê config/series.yaml e sincroniza o catálogo staging.serie."""
        return pipeline.preparar_series()

    # No máximo 3 consultas simultâneas à API pública por execução.
    @task(map_index_template="{{ serie_label }}", max_active_tis_per_dagrun=3)
    def extrair_raw(serie: dict[str, Any]) -> dict[str, Any]:
        """Uma task por série: busca na API e grava em raw.sgs_payload."""
        context = get_current_context()
        context["serie_label"] = f"{serie['codigo']} - {serie['nome']}"
        dag_run = context["dag_run"]

        backfill = None
        if str(dag_run.run_type).lower().endswith("backfill"):
            backfill = (
                _data_local(context["data_interval_start"]),
                _data_local(context["data_interval_end"]),
            )
        resultado = pipeline.extrair_serie(
            SerieConfig.from_dict(serie),
            fim=_data_local(context.get("data_interval_end")),
            run_id=dag_run.run_id,
            backfill=backfill,
        )
        return {**asdict(resultado), "nome": serie["nome"]}

    @task(map_index_template="{{ serie_label }}")
    def carregar_staging(extracao: dict[str, Any]) -> dict[str, int]:
        """Converte os payloads do raw e faz upsert em staging.serie_valor."""
        context = get_current_context()
        context["serie_label"] = f"{extracao['serie_id']} - {extracao['nome']}"
        return pipeline.carregar_staging(extracao["serie_id"], extracao["raw_ids"])

    extracoes = extrair_raw.expand(serie=preparar_series())
    carregar_staging.expand(extracao=extracoes)


bcb_indicadores()
