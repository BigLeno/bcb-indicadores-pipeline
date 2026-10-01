"""A DAG importa sem erro e tem a estrutura esperada (não executa tasks).

Usa `dagbag.dags` (resultado do parse, em memória) e não `get_dag()`, que consulta o
metadata DB do Airflow: o teste precisa rodar sem banco nenhum, como no CI.
"""

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
