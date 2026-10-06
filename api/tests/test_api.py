from collections.abc import Callable
from datetime import date

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

Carregar = Callable[[int, list[tuple[date, str]]], None]


def _meses(ano: int, n: int) -> list[date]:
    return [date(ano + i // 12, i % 12 + 1, 1) for i in range(n)]


def test_health(client: APIClient) -> None:
    resposta = client.get("/api/health/")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_root_lists_endpoints(client: APIClient) -> None:
    corpo = client.get("/api/").json()

    assert {"series", "valores", "marts/ipca-mensal", "marts/dolar-diario"} <= corpo.keys()


def test_series_catalog(client: APIClient, carregar: Carregar) -> None:
    carregar(11, [(date(2024, 1, 2), "0.043739")])

    lista = client.get("/api/series/").json()
    detalhe = client.get("/api/series/11/").json()

    assert [s["serie_id"] for s in lista] == [11]
    assert detalhe["nome"] == "Taxa Selic diária"
    assert client.get("/api/series/999/").status_code == 404


def test_valores_filtered_by_serie_and_period(client: APIClient, carregar: Carregar) -> None:
    carregar(11, [(date(2024, 1, d), "0.04") for d in (2, 3, 4, 5)])
    carregar(12, [(date(2024, 1, 3), "0.039")])

    corpo = client.get(
        "/api/valores/", {"serie": 11, "data_inicio": "2024-01-03", "data_fim": "2024-01-04"}
    ).json()

    assert corpo["count"] == 2
    assert [(v["serie_id"], v["data"]) for v in corpo["results"]] == [
        (11, "2024-01-03"),
        (11, "2024-01-04"),
    ]


def test_decimal_is_exact_string(client: APIClient, carregar: Carregar) -> None:
    carregar(11, [(date(2024, 1, 2), "0.043739")])

    valor = client.get("/api/valores/", {"serie": 11}).json()["results"][0]["valor"]

    assert valor == "0.043739"  # sem arredondar nem completar casas


def test_pagination_and_page_size_cap(client: APIClient, carregar: Carregar) -> None:
    carregar(1, [(date(2024, 1, d), "5") for d in range(1, 31)])

    pagina = client.get("/api/marts/dolar-diario/", {"page_size": 10, "page": 2}).json()
    teto = client.get("/api/marts/dolar-diario/", {"page_size": 100000}).json()

    assert pagina["count"] == 30
    assert len(pagina["results"]) == 10
    assert pagina["previous"] is not None
    assert pagina["next"] is not None
    assert len(teto["results"]) == 30  # page_size acima do teto cai para 1000


def test_ordering_descending(client: APIClient, carregar: Carregar) -> None:
    carregar(1, [(date(2024, 1, 2), "5"), (date(2024, 1, 3), "5.5")])

    datas = [
        r["data"] for r in client.get("/api/marts/dolar-diario/?ordering=-data").json()["results"]
    ]

    assert datas == ["2024-01-03", "2024-01-02"]


@pytest.mark.parametrize(
    "params",
    [
        {"data_inicio": "31/12/2024"},  # formato errado
        {"data_inicio": "2024-02-30"},  # data inexistente
        {"data_inicio": "2024-12-01", "data_fim": "2024-01-01"},  # período invertido
    ],
)
def test_invalid_period_returns_400(client: APIClient, params: dict[str, str]) -> None:
    assert client.get("/api/marts/ipca-mensal/", params).status_code == 400


def test_ipca_mart_with_accumulated_values(client: APIClient, carregar: Carregar) -> None:
    carregar(433, [(m, "1") for m in _meses(2023, 12)])

    dezembro = client.get("/api/marts/ipca-mensal/2023-12-01/").json()
    periodo = client.get(
        "/api/marts/ipca-mensal/", {"data_inicio": "2023-06-01", "data_fim": "2023-08-31"}
    ).json()

    assert dezembro == {
        "mes": "2023-12-01",
        "variacao_mensal_pct": "1",  # exatamente como gravado
        "acumulado_ano_pct": "12.682503",
        "acumulado_12m_pct": "12.682503",
    }
    assert [r["mes"] for r in periodo["results"]] == ["2023-06-01", "2023-07-01", "2023-08-01"]
    assert periodo["results"][0]["acumulado_12m_pct"] is None


def test_cdi_and_dolar_monthly_marts(client: APIClient, carregar: Carregar) -> None:
    carregar(12, [(date(2024, 1, 2), "0.04"), (date(2024, 1, 3), "0.04")])
    carregar(1, [(date(2024, 1, 31), "5.00"), (date(2024, 2, 29), "4.50")])

    cdi = client.get("/api/marts/cdi-mensal/2024-01-01/").json()
    dolar = client.get("/api/marts/dolar-mensal/", {"data_inicio": "2024-02-01"}).json()

    assert cdi["acumulado_mes_pct"] == "0.080016"
    assert cdi["dias_uteis"] == 2
    assert dolar["results"] == [
        {
            "mes": "2024-02-01",
            "data_fechamento": "2024-02-29",
            "cotacao_fechamento": "4.50",
            "variacao_mensal_pct": "-10.000000",
        }
    ]


def test_mart_detail_404_and_bad_date_in_url(client: APIClient) -> None:
    assert client.get("/api/marts/ipca-mensal/1999-01-01/").status_code == 404
    assert client.get("/api/marts/ipca-mensal/janeiro/").status_code == 404


@pytest.mark.parametrize("metodo", ["post", "put", "patch", "delete"])
def test_api_is_read_only(client: APIClient, metodo: str) -> None:
    resposta = getattr(client, metodo)("/api/marts/ipca-mensal/", {})

    assert resposta.status_code == 405


def test_openapi_schema_and_docs(client: APIClient) -> None:
    schema = client.get("/api/schema/?format=json")
    docs = client.get("/api/docs/")

    assert schema.status_code == 200
    paths = schema.json()["paths"]
    assert "/api/marts/ipca-mensal/" in paths
    parametros = {p["name"] for p in paths["/api/valores/"]["get"]["parameters"]}
    assert {"serie", "data_inicio", "data_fim", "page", "page_size", "ordering"} <= parametros
    assert docs.status_code == 200
    assert b"swagger" in docs.content.lower()


def test_openapi_describes_the_key_in_detail_urls(client: APIClient) -> None:
    paths = client.get("/api/schema/?format=json").json()["paths"]

    def descricao(caminho: str) -> str:
        (parametro,) = (p for p in paths[caminho]["get"]["parameters"] if p["in"] == "path")
        return parametro["description"]

    assert "Fins de semana" in descricao("/api/marts/dolar-diario/{data}/")
    assert "AAAA-MM-01" in descricao("/api/marts/ipca-mensal/{mes}/")
    assert "Código SGS" in descricao("/api/series/{serie_id}/")
