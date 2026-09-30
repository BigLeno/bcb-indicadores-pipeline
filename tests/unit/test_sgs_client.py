"""Client SGS com respostas simuladas por httpx.MockTransport (sem rede)."""

from collections.abc import Callable
from datetime import date

import httpx
import pytest

from bcb_pipeline.sgs_client import SgsClient, SgsResponseError, SgsTransientError

Handler = Callable[[httpx.Request], httpx.Response]
JSON = {"Content-Type": "application/json; charset=utf-8"}
NOT_FOUND = {
    "erro": {
        "statusCode": 404,
        "detail": "br.gov.bcb.pec.sgs.comum.excecoes.SGSNegocioException: Value(s) not found",
    }
}


class Recorder:
    """Guarda as requisições e as esperas, para inspecionar retry e paginação."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, Exception):
            raise response
        return response

    def client(self, **kwargs: int) -> SgsClient:
        http = httpx.Client(
            transport=httpx.MockTransport(self.handler), base_url="https://sgs.test"
        )
        return SgsClient(http, backoff_seconds=1.0, sleep=self.sleeps.append, **kwargs)


def test_returns_records_and_sends_brazilian_dates() -> None:
    body = [{"data": "02/01/2024", "valor": "0.043739"}]
    rec = Recorder(httpx.Response(200, json=body, headers=JSON))

    registros = rec.client().fetch_window(11, date(2024, 1, 2), date(2024, 1, 31))

    assert registros == body
    request = rec.requests[0]
    assert request.url.path == "/bcdata.sgs.11/dados"
    assert request.url.params["dataInicial"] == "02/01/2024"
    assert request.url.params["dataFinal"] == "31/01/2024"
    assert request.url.params["formato"] == "json"


@pytest.mark.parametrize("status", [404, 200])
def test_not_found_error_means_empty_window(status: int) -> None:
    rec = Recorder(httpx.Response(status, json=NOT_FOUND, headers=JSON))

    assert rec.client().fetch_window(1, date(2026, 9, 27), date(2026, 9, 27)) == []
    assert len(rec.requests) == 1


def test_empty_list_is_valid() -> None:
    rec = Recorder(httpx.Response(200, json=[], headers=JSON))

    assert rec.client().fetch_window(433, date(2026, 9, 1), date(2026, 9, 30)) == []


HTML = {"Content-Type": "text/html; charset=utf-8"}
PAGINA_ERRO = "<html><title>Requisição inválida!</title></html>"


@pytest.mark.parametrize("status", [200, 502])
def test_gateway_html_page_is_retried(status: int) -> None:
    body = [{"data": "01/01/2010", "valor": "8.75"}]
    rec = Recorder(
        httpx.Response(status, text=PAGINA_ERRO, headers=HTML),
        httpx.Response(200, json=body, headers=JSON),
    )

    assert rec.client().fetch_window(432, date(2010, 1, 1), date(2014, 12, 31)) == body
    assert len(rec.requests) == 2


def test_persistent_html_page_fails_with_hint_about_series_code() -> None:
    rec = Recorder(httpx.Response(200, text=PAGINA_ERRO, headers=HTML))

    with pytest.raises(SgsTransientError, match="código da série existe"):
        rec.client(max_attempts=3).fetch_window(99999999, date(2024, 1, 1), date(2024, 1, 31))
    assert len(rec.requests) == 3


def test_406_window_too_large_fails_without_retry() -> None:
    body = {"error": "O sistema aceita uma janela de consulta de, no máximo, 10 anos"}
    rec = Recorder(httpx.Response(406, json=body, headers=JSON))

    with pytest.raises(SgsResponseError, match=r"HTTP 406.*10 anos"):
        rec.client().fetch_window(11, date(2010, 1, 1), date(2024, 12, 31))
    assert rec.sleeps == []


def test_other_404_is_not_treated_as_empty() -> None:
    rec = Recorder(httpx.Response(404, json={"erro": {"detail": "rota inexistente"}}, headers=JSON))

    with pytest.raises(SgsResponseError, match="HTTP 404"):
        rec.client().fetch_window(11, date(2024, 1, 1), date(2024, 1, 31))


def test_json_that_is_not_a_list_fails() -> None:
    rec = Recorder(httpx.Response(200, json={"inesperado": True}, headers=JSON))

    with pytest.raises(SgsResponseError, match="esperava uma lista"):
        rec.client().fetch_window(11, date(2024, 1, 1), date(2024, 1, 31))


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_transient_status_is_retried_until_success(status: int) -> None:
    body = [{"data": "02/01/2024", "valor": "1"}]
    rec = Recorder(
        httpx.Response(status, headers=JSON, json={}),
        httpx.Response(200, json=body, headers=JSON),
    )

    assert rec.client().fetch_window(11, date(2024, 1, 1), date(2024, 1, 31)) == body
    assert len(rec.requests) == 2
    assert len(rec.sleeps) == 1


def test_timeout_is_retried_with_exponential_backoff() -> None:
    rec = Recorder(httpx.ReadTimeout("lento"))

    with pytest.raises(SgsTransientError, match=r"ReadTimeout.*após 4 tentativas"):
        rec.client(max_attempts=4).fetch_window(11, date(2024, 1, 1), date(2024, 1, 31))

    assert len(rec.requests) == 4
    # base 1s dobrando a cada tentativa, com até 25% de jitter
    for espera, base in zip(rec.sleeps, [1, 2, 4], strict=True):
        assert base <= espera <= base * 1.25


def test_retry_after_header_is_respected() -> None:
    rec = Recorder(
        httpx.Response(429, headers={**JSON, "Retry-After": "7"}, json={}),
        httpx.Response(200, json=[], headers=JSON),
    )

    rec.client().fetch_window(11, date(2024, 1, 1), date(2024, 1, 31))

    assert 7 <= rec.sleeps[0] <= 7 * 1.25


def test_fetch_range_paginates_in_windows() -> None:
    rec = Recorder(httpx.Response(200, json=[], headers=JSON))

    client = rec.client(window_years=10)
    respostas = list(client.fetch_range(11, date(2000, 1, 1), date(2026, 9, 30)))

    pedidas = [(r.url.params["dataInicial"], r.url.params["dataFinal"]) for r in rec.requests]
    assert pedidas == [
        ("01/01/2000", "31/12/2009"),
        ("01/01/2010", "31/12/2019"),
        ("01/01/2020", "30/09/2026"),
    ]
    assert (respostas[0].inicio, respostas[0].fim) == (date(2000, 1, 1), date(2009, 12, 31))
