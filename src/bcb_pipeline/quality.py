"""Checagens de qualidade do staging. Qualquer violação falha a task."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import psycopg

from bcb_pipeline.config import SerieConfig

AMOSTRA = 5


class QualityCheckError(RuntimeError):
    """Uma ou mais checagens encontraram violações."""


@dataclass(frozen=True)
class CheckResult:
    """Resultado de uma checagem: quantas linhas violam a regra e uma amostra delas."""

    nome: str
    violacoes: int
    amostra: list[tuple[Any, ...]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.violacoes == 0


# Cada checagem é uma consulta que devolve as linhas que violam a regra.
_CHECKS: dict[str, str] = {
    "serie_sem_dados": """
        SELECT %(serie_id)s
         WHERE NOT EXISTS (SELECT 1 FROM staging.serie_valor WHERE serie_id = %(serie_id)s)
    """,
    # Redundante com o NOT NULL do schema, de propósito: protege contra mudança no DDL.
    "valores_nulos": """
        SELECT data, valor FROM staging.serie_valor
         WHERE serie_id = %(serie_id)s AND (data IS NULL OR valor IS NULL)
    """,
    "datas_futuras": """
        SELECT data, valor FROM staging.serie_valor
         WHERE serie_id = %(serie_id)s AND data > %(hoje)s
    """,
    "datas_duplicadas": """
        SELECT data, count(*) FROM staging.serie_valor
         WHERE serie_id = %(serie_id)s
         GROUP BY data HAVING count(*) > 1
    """,
    "fora_da_faixa": """
        SELECT data, valor FROM staging.serie_valor
         WHERE serie_id = %(serie_id)s AND (valor < %(minimo)s OR valor > %(maximo)s)
    """,
}


def executar_checagens(
    conn: psycopg.Connection, serie: SerieConfig, hoje: date
) -> list[CheckResult]:
    """Roda todas as checagens da série. `fora_da_faixa` só roda se a série tem `faixa`."""
    params: dict[str, Any] = {"serie_id": serie.codigo, "hoje": hoje}
    if serie.faixa is not None:
        params |= {"minimo": serie.faixa.minimo, "maximo": serie.faixa.maximo}

    resultados = []
    for nome, consulta in _CHECKS.items():
        if nome == "fora_da_faixa" and serie.faixa is None:
            continue
        # Conta tudo, mas traz só uma amostra para o log.
        total = conn.execute(f"SELECT count(*) FROM ({consulta}) v", params).fetchone()
        amostra = conn.execute(f"{consulta} LIMIT {AMOSTRA}", params).fetchall()
        resultados.append(CheckResult(nome, total[0] if total else 0, amostra))
    return resultados


def exigir_aprovacao(serie: SerieConfig, resultados: list[CheckResult]) -> None:
    """Levanta `QualityCheckError` descrevendo as checagens que falharam."""
    falhas = [r for r in resultados if not r.ok]
    if falhas:
        detalhes = "; ".join(f"{r.nome}: {r.violacoes} (ex.: {r.amostra})" for r in falhas)
        raise QualityCheckError(f"série {serie.codigo} reprovada na qualidade -> {detalhes}")
