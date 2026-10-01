"""Pipeline de ponta a ponta no Postgres de teste, com a API SGS simulada."""

from datetime import date
from decimal import Decimal

import httpx
import psycopg
import pytest

from bcb_pipeline import pipeline
from bcb_pipeline.config import Faixa, SerieConfig
from bcb_pipeline.quality import QualityCheckError
from bcb_pipeline.sgs_client import SgsClient

JSON = {"Content-Type": "application/json"}
NOT_FOUND = {"erro": {"statusCode": 404, "detail": "SGSNegocioException: Value(s) not found"}}
DOLAR = SerieConfig(
    1, "Dólar", "diaria", "R$/US$", date(2026, 9, 28), Faixa(Decimal(1), Decimal(10))
)
API = {
    ("28/09/2026", "30/09/2026"): [
        {"data": "28/09/2026", "valor": "5.2132"},
        {"data": "29/09/2026", "valor": "5.2204"},
        {"data": "30/09/2026", "valor": "5.1809"},
    ],
}


def _client(respostas: dict[tuple[str, str], list[dict[str, str]]]) -> SgsClient:
    def handler(request: httpx.Request) -> httpx.Response:
        chave = (request.url.params["dataInicial"], request.url.params["dataFinal"])
        if chave in respostas:
            return httpx.Response(200, json=respostas[chave], headers=JSON)
        return httpx.Response(404, json=NOT_FOUND, headers=JSON)

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://sgs.test")
    return SgsClient(http, sleep=lambda _: None)


def _rodar(fim: date, respostas: dict[tuple[str, str], list[dict[str, str]]]) -> dict[str, int]:
    """Uma execução da DAG para uma série, na mesma ordem das tasks."""
    extracao = pipeline.extrair_serie(DOLAR, fim=fim, run_id="teste", client=_client(respostas))
    return pipeline.carregar_staging(extracao.serie_id, extracao.raw_ids)


@pytest.mark.usefixtures("warehouse_env")
def test_second_run_does_not_duplicate(conn: psycopg.Connection) -> None:
    conn.execute(
        "INSERT INTO staging.serie (serie_id, nome, periodicidade, unidade)"
        " VALUES (1, 'Dólar', 'diaria', 'R$/US$')"
    )
    conn.commit()

    primeira = _rodar(date(2026, 9, 30), API)
    # Segunda execução: começa na última data carregada (30/09), que a API devolve de novo.
    segunda = _rodar(
        date(2026, 9, 30), {("30/09/2026", "30/09/2026"): API[("28/09/2026", "30/09/2026")][2:]}
    )

    assert (primeira["inseridas"], primeira["atualizadas"]) == (3, 0)
    assert (segunda["inseridas"], segunda["atualizadas"], segunda["inalteradas"]) == (0, 0, 1)
    assert conn.execute("SELECT count(*) FROM staging.serie_valor").fetchone() == (3,)

    pipeline.checar_qualidade(DOLAR, hoje=date(2026, 9, 30))
    assert pipeline.atualizar_marts()["dolar_diario"] == 3


@pytest.mark.usefixtures("warehouse_env")
def test_quality_failure_blocks_with_clear_error(conn: psycopg.Connection) -> None:
    conn.execute(
        "INSERT INTO staging.serie (serie_id, nome, periodicidade, unidade)"
        " VALUES (1, 'Dólar', 'diaria', 'R$/US$')"
    )
    conn.commit()
    _rodar(
        date(2026, 9, 30),
        {("28/09/2026", "30/09/2026"): [{"data": "28/09/2026", "valor": "52.13"}]},
    )

    with pytest.raises(QualityCheckError, match="fora_da_faixa: 1"):
        pipeline.checar_qualidade(DOLAR, hoje=date(2026, 9, 30))
