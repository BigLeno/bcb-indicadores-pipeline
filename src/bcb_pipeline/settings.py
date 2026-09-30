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
