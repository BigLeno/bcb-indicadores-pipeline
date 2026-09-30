"""Configuração do pipeline lida de variáveis de ambiente."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from psycopg.conninfo import make_conninfo


class MissingSettingError(RuntimeError):
    """Variável de ambiente obrigatória ausente."""


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not value:
        raise MissingSettingError(f"variável de ambiente obrigatória não definida: {name}")
    return value


@dataclass(frozen=True)
class SgsSettings:
    """Parâmetros de acesso à API SGS. Todos têm padrão; ajuste por `SGS_*`."""

    base_url: str = "https://api.bcb.gov.br/dados/serie"
    timeout_seconds: float = 60.0
    max_attempts: int = 4
    backoff_seconds: float = 2.0
    # A API aceita até 10 anos, mas 10 anos de série diária levam ~20 s e o gateway
    # corta em ~30 s. Com 5 anos cada consulta fica longe do limite.
    window_years: int = 5

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> SgsSettings:
        """Lê as variáveis `SGS_*`, caindo nos padrões quando ausentes."""
        env = os.environ if env is None else env
        default = cls()
        return cls(
            base_url=env.get("SGS_BASE_URL", default.base_url),
            timeout_seconds=float(env.get("SGS_TIMEOUT_SECONDS", default.timeout_seconds)),
            max_attempts=int(env.get("SGS_MAX_ATTEMPTS", default.max_attempts)),
            backoff_seconds=float(env.get("SGS_BACKOFF_SECONDS", default.backoff_seconds)),
            window_years=int(env.get("SGS_WINDOW_YEARS", default.window_years)),
        )


@dataclass(frozen=True)
class WarehouseSettings:
    """Credenciais do Postgres do pipeline (separado do metadata DB do Airflow)."""

    host: str
    port: int
    dbname: str
    user: str
    password: str = field(repr=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> WarehouseSettings:
        """Lê as variáveis `WAREHOUSE_*`."""
        env = os.environ if env is None else env
        return cls(
            host=_require(env, "WAREHOUSE_HOST"),
            port=int(env.get("WAREHOUSE_PORT", "5432")),
            dbname=_require(env, "WAREHOUSE_DB"),
            user=_require(env, "WAREHOUSE_USER"),
            password=_require(env, "WAREHOUSE_PASSWORD"),
        )

    @property
    def conninfo(self) -> str:
        """String de conexão no formato libpq."""
        return make_conninfo(
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            user=self.user,
            password=self.password,
            application_name="bcb_pipeline",
        )
