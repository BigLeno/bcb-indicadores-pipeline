"""Executor mínimo de migrations em SQL puro, numeradas (`001_nome.sql`).

Cada arquivo é aplicado uma única vez e registrado em `public.schema_migrations`
com o seu checksum. Um arquivo já aplicado não pode ser editado: a mudança vira
uma migration nova.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

from bcb_pipeline.acesso import garantir_usuario_leitura
from bcb_pipeline.settings import WarehouseSettings

logger = logging.getLogger(__name__)

MIGRATION_FILE = re.compile(r"^(?P<version>\d{3})_(?P<name>[a-z0-9_]+)\.sql$")
# Chave arbitrária e fixa: impede que duas execuções migrem o banco ao mesmo tempo.
ADVISORY_LOCK_KEY = 7_411_520_001


class MigrationError(RuntimeError):
    """Conjunto de migrations inválido ou divergente do que já foi aplicado."""


@dataclass(frozen=True)
class Migration:
    """Um arquivo de migration lido do disco."""

    version: str
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        """SHA-256 do conteúdo, para detectar edição de migration já aplicada."""
        return hashlib.sha256(self.sql.encode()).hexdigest()


def discover(directory: Path) -> list[Migration]:
    """Lê as migrations do diretório, em ordem de versão."""
    migrations: dict[str, Migration] = {}
    for path in sorted(directory.glob("*.sql")):
        match = MIGRATION_FILE.match(path.name)
        if match is None:
            raise MigrationError(f"nome fora do padrão NNN_nome.sql: {path.name}")
        version = match["version"]
        if version in migrations:
            raise MigrationError(f"versão duplicada: {version}")
        migrations[version] = Migration(version, match["name"], path.read_text(encoding="utf-8"))
    return [migrations[v] for v in sorted(migrations)]


def apply(conn: psycopg.Connection, migrations: list[Migration]) -> list[Migration]:
    """Aplica as migrations pendentes numa única transação e devolve as aplicadas."""
    applied_now: list[Migration] = []
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_KEY,))
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS public.schema_migrations (
                version    text PRIMARY KEY,
                name       text NOT NULL,
                checksum   text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        rows = conn.execute("SELECT version, checksum FROM public.schema_migrations").fetchall()
        already_applied = dict(rows)

        for migration in migrations:
            stored_checksum = already_applied.get(migration.version)
            if stored_checksum is not None:
                if stored_checksum != migration.checksum:
                    raise MigrationError(
                        f"migration {migration.version}_{migration.name} foi editada "
                        "depois de aplicada; crie uma migration nova"
                    )
                continue
            logger.info("aplicando migration %s_%s", migration.version, migration.name)
            conn.execute(migration.sql)  # type: ignore[arg-type]  # SQL vem de arquivo versionado
            conn.execute(
                "INSERT INTO public.schema_migrations (version, name, checksum)"
                " VALUES (%s, %s, %s)",
                (migration.version, migration.name, migration.checksum),
            )
            applied_now.append(migration)
    return applied_now


def main() -> None:
    """Ponto de entrada: `python -m bcb_pipeline.migrate`."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    directory = Path(os.environ.get("MIGRATIONS_DIR", "sql/migrations"))
    migrations = discover(directory)
    settings = WarehouseSettings.from_env()
    with psycopg.connect(settings.conninfo) as conn:
        applied = apply(conn, migrations)
        logger.info(
            "migrations concluídas: %d aplicadas agora, %d no total",
            len(applied),
            len(migrations),
        )
        usuario, senha = os.environ.get("API_DB_USER"), os.environ.get("API_DB_PASSWORD")
        if usuario and senha:
            criado = garantir_usuario_leitura(conn, usuario, senha)
            logger.info("usuário de leitura da API %s: %s", "criado" if criado else "ok", usuario)


if __name__ == "__main__":
    main()
