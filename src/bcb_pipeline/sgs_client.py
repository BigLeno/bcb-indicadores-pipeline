"""Client HTTP da API SGS do Banco Central.

Comportamento observado na API (set/2026), que este módulo trata:
- séries diárias exigem `dataInicial`/`dataFinal` e aceitam no máximo 10 anos
  por consulta; fora disso a resposta é HTTP 406;
- janela sem observações responde `{"erro": {... "Value(s) not found"}}` em vez de
  lista vazia, às vezes com HTTP 404 e às vezes com HTTP 200;
- quando o backend demora (~30 s) ou falha, o gateway devolve uma página HTML genérica
  ("Requisição inválida"), com HTTP 200 ou 502. É o mesmo HTML para série inexistente,
  então não dá para distinguir os casos: HTML é tratado como transitório;
- 429 e 5xx também são transitórios e merecem nova tentativa.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from types import TracebackType
from typing import Any

import httpx
import structlog

from bcb_pipeline.settings import SgsSettings
from bcb_pipeline.transform import janelas

logger = structlog.get_logger(__name__)

USER_AGENT = "bcb-indicadores-pipeline/0.1"
MAX_RETRY_AFTER_SECONDS = 60.0


class SgsError(Exception):
    """Erro ao consultar a API SGS."""


class SgsTransientError(SgsError):
    """Falha temporária (timeout, 429, 5xx, página HTML) que persistiu após as tentativas."""


class SgsResponseError(SgsError):
    """Resposta que não se resolve tentando de novo (4xx em JSON, JSON inesperado)."""


@dataclass(frozen=True)
class JanelaResposta:
    """Resposta de uma consulta: a janela pedida e os registros como vieram."""

    inicio: date
    fim: date
    registros: list[dict[str, Any]]


def _formatar(dia: date) -> str:
    return dia.strftime("%d/%m/%Y")


def _falha_transitoria(response: httpx.Response) -> str | None:
    """Motivo da falha se a resposta merece nova tentativa; None se é definitiva."""
    if response.status_code == 429 or response.status_code >= 500:
        return f"HTTP {response.status_code}"
    content_type = response.headers.get("Content-Type", "")
    if "json" not in content_type:
        return f"HTTP {response.status_code} com {content_type or 'corpo sem Content-Type'}"
    return None


def _sem_valores(body: Any) -> bool:
    """Detecta o erro "Value(s) not found", que a API usa para janela sem observações."""
    erro = body.get("erro") if isinstance(body, dict) else None
    return isinstance(erro, dict) and "not found" in str(erro.get("detail", "")).lower()


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return min(float(response.headers["Retry-After"]), MAX_RETRY_AFTER_SECONDS)
    except (KeyError, ValueError):
        return None


class SgsClient:
    """Consulta séries SGS em janelas de datas, com retry para falhas transitórias."""

    def __init__(
        self,
        http: httpx.Client,
        *,
        max_attempts: int = 4,
        backoff_seconds: float = 2.0,
        window_years: int = 5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = http
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._window_years = window_years
        self._sleep = sleep

    @classmethod
    def from_settings(cls, settings: SgsSettings | None = None) -> SgsClient:
        """Cria o client com o `httpx.Client` configurado pelas variáveis `SGS_*`."""
        settings = settings or SgsSettings.from_env()
        http = httpx.Client(
            base_url=settings.base_url,
            timeout=httpx.Timeout(settings.timeout_seconds, connect=10.0),
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        return cls(
            http,
            max_attempts=settings.max_attempts,
            backoff_seconds=settings.backoff_seconds,
            window_years=settings.window_years,
        )

    def __enter__(self) -> SgsClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._http.close()

    def fetch_range(self, codigo: int, inicio: date, fim: date) -> Iterator[JanelaResposta]:
        """Busca [inicio, fim] (inclusivo) dividindo em janelas aceitas pela API."""
        for janela_inicio, janela_fim in janelas(inicio, fim, self._window_years):
            registros = self.fetch_window(codigo, janela_inicio, janela_fim)
            yield JanelaResposta(janela_inicio, janela_fim, registros)

    def fetch_window(self, codigo: int, inicio: date, fim: date) -> list[dict[str, Any]]:
        """Busca uma única janela. Janela sem dados devolve lista vazia."""
        params = {"formato": "json", "dataInicial": _formatar(inicio), "dataFinal": _formatar(fim)}
        url = f"/bcdata.sgs.{codigo}/dados"
        log = logger.bind(
            serie_id=codigo, janela_inicio=inicio.isoformat(), janela_fim=fim.isoformat()
        )

        for tentativa in range(1, self._max_attempts + 1):
            inicio_req = time.monotonic()
            try:
                response = self._http.get(url, params=params)
            except httpx.TransportError as exc:  # timeout, conexão recusada, DNS...
                motivo, espera_sugerida = f"{type(exc).__name__}: {exc}", None
            else:
                motivo = _falha_transitoria(response)
                if motivo is None:
                    registros = self._interpretar(response, codigo)
                    log.info(
                        "sgs_janela_consultada",
                        http_status=response.status_code,
                        registros=len(registros),
                        tentativa=tentativa,
                        duracao_s=round(time.monotonic() - inicio_req, 2),
                    )
                    return registros
                espera_sugerida = _retry_after(response)

            if tentativa == self._max_attempts:
                raise SgsTransientError(
                    f"série {codigo}, janela {inicio}..{fim}: {motivo} "
                    f"após {self._max_attempts} tentativas "
                    "(se persistir, confira se o código da série existe no SGS)"
                )
            # Backoff exponencial com jitter, para as tasks paralelas não baterem juntas.
            espera = espera_sugerida or self._backoff_seconds * 2 ** (tentativa - 1)
            espera *= 1 + random.random() * 0.25
            log.warning(
                "sgs_tentativa_falhou",
                motivo=motivo,
                tentativa=tentativa,
                espera_s=round(espera, 2),
            )
            self._sleep(espera)

        raise AssertionError("inalcançável")  # pragma: no cover

    @staticmethod
    def _interpretar(response: httpx.Response, codigo: int) -> list[dict[str, Any]]:
        try:
            body = response.json()
        except ValueError as exc:
            raise SgsResponseError(f"série {codigo}: JSON inválido") from exc

        if _sem_valores(body):
            return []
        if response.status_code != 200:
            detalhe = (body.get("error") or body.get("erro")) if isinstance(body, dict) else body
            raise SgsResponseError(f"série {codigo}: HTTP {response.status_code}: {detalhe}")
        if not isinstance(body, list):
            tipo = type(body).__name__
            raise SgsResponseError(f"série {codigo}: esperava uma lista, veio {tipo}")
        return body
