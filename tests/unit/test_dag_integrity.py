"""A DAG importa sem erro e tem a estrutura esperada (não executa tasks)."""

from pathlib import Path

import pytest

pytest.importorskip("airflow")

from airflow.dag_processing.dagbag import DagBag

DAGS_DIR = Path(__file__).resolve().parents[2] / "dags"


@pytest.fixture(scope="module")
def dagbag() -> DagBag:
    return DagBag(dag_folder=DAGS_DIR)


def test_no_import_errors(dagbag: DagBag) -> None:
    assert dagbag.import_errors == {}


def test_bcb_indicadores_structure(dagbag: DagBag) -> None:
    dag = dagbag.get_dag("bcb_indicadores")

    assert dag is not None
    assert set(dag.task_ids) == {"preparar_series", "extrair_raw", "carregar_staging"}
    assert dag.get_task("carregar_staging").upstream_task_ids == {"extrair_raw"}
    assert dag.catchup is False
    assert dag.max_active_runs == 1


def test_tasks_have_retries_with_backoff(dagbag: DagBag) -> None:
    for task in dagbag.get_dag("bcb_indicadores").tasks:
        assert task.retries >= 3
        assert task.retry_exponential_backoff
