"""A DAG importa sem erro e tem a estrutura esperada.

A única task executada aqui é `extrair_raw`, com o pipeline substituído por um dublê,
para conferir como os erros da API viram (ou não) retry no Airflow.

Usa `dagbag.dags` (resultado do parse, em memória) e não `get_dag()`, que consulta o
metadata DB do Airflow: o teste precisa rodar sem banco nenhum, como no CI.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("airflow")

from airflow.dag_processing.dagbag import DagBag
from airflow.sdk.exceptions import AirflowFailException

from bcb_pipeline.sgs_client import SgsResponseError, SgsTransientError

DAGS_DIR = Path(__file__).resolve().parents[2] / "dags"


@pytest.fixture(scope="module")
def dagbag() -> DagBag:
    return DagBag(dag_folder=DAGS_DIR)


def test_no_import_errors(dagbag: DagBag) -> None:
    assert dagbag.import_errors == {}


def test_bcb_indicadores_structure(dagbag: DagBag) -> None:
    dag = dagbag.dags["bcb_indicadores"]

    assert set(dag.task_ids) == {
        "preparar_series",
        "extrair_raw",
        "carregar_staging",
        "checar_qualidade",
        "atualizar_marts",
    }
    assert dag.get_task("carregar_staging").upstream_task_ids == {"extrair_raw"}
    assert dag.get_task("checar_qualidade").upstream_task_ids == {"carregar_staging"}
    assert dag.get_task("atualizar_marts").upstream_task_ids == {"checar_qualidade"}
    assert dag.catchup is False
    assert dag.max_active_runs == 1


def test_tasks_have_retries_with_backoff(dagbag: DagBag) -> None:
    for task in dagbag.dags["bcb_indicadores"].tasks:
        if task.task_id == "checar_qualidade":
            assert task.retries == 0  # dado ruim não melhora tentando de novo
            continue
        assert task.retries >= 3
        assert task.retry_exponential_backoff


@pytest.mark.parametrize(
    ("erro", "esperado"),
    [
        (SgsResponseError("série 1: HTTP 406"), AirflowFailException),  # definitivo: sem retry
        (SgsTransientError("série 1: HTTP 502"), SgsTransientError),  # transitório: com retry
    ],
)
def test_extrair_raw_skips_retries_only_for_definitive_errors(
    dagbag: DagBag, monkeypatch: pytest.MonkeyPatch, erro: Exception, esperado: type
) -> None:
    funcao = dagbag.dags["bcb_indicadores"].get_task("extrair_raw").python_callable
    contexto = {"dag_run": SimpleNamespace(run_type="manual", run_id="teste")}

    def falhar(*_: object, **__: object) -> None:
        raise erro

    monkeypatch.setitem(funcao.__globals__, "get_current_context", lambda: contexto)
    monkeypatch.setitem(funcao.__globals__, "pipeline", SimpleNamespace(extrair_serie=falhar))
    serie = {
        "codigo": 1,
        "nome": "Dólar",
        "periodicidade": "diaria",
        "unidade": "R$/US$",
        "inicio": "2000-01-01",
        "faixa": None,
        "variacao_max_pct": None,
    }

    with pytest.raises(esperado):
        funcao(serie)
