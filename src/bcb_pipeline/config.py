"""Leitura e validação de `config/series.yaml`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

import yaml

Periodicidade = Literal["diaria", "mensal"]
PERIODICIDADES: frozenset[str] = frozenset({"diaria", "mensal"})
DEFAULT_CONFIG_PATH = Path("config/series.yaml")


class ConfigError(ValueError):
    """Arquivo de configuração das séries inválido."""


@dataclass(frozen=True)
class Faixa:
    """Intervalo [minimo, maximo] de valores plausíveis, usado pela checagem de qualidade."""

    minimo: Decimal
    maximo: Decimal


@dataclass(frozen=True)
class SerieConfig:
    """Uma série SGS configurada no pipeline."""

    codigo: int
    nome: str
    periodicidade: Periodicidade
    unidade: str
    inicio: date
    faixa: Faixa | None = None

    def to_dict(self) -> dict[str, Any]:
        """Versão serializável (XCom do Airflow só aceita tipos simples)."""
        return {
            "codigo": self.codigo,
            "nome": self.nome,
            "periodicidade": self.periodicidade,
            "unidade": self.unidade,
            "inicio": self.inicio.isoformat(),
            "faixa": (
                [str(self.faixa.minimo), str(self.faixa.maximo)] if self.faixa is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SerieConfig:
        """Inverso de `to_dict`."""
        faixa = data.get("faixa")
        return cls(
            codigo=data["codigo"],
            nome=data["nome"],
            periodicidade=data["periodicidade"],
            unidade=data["unidade"],
            inicio=date.fromisoformat(data["inicio"]),
            faixa=Faixa(Decimal(faixa[0]), Decimal(faixa[1])) if faixa else None,
        )


def _parse_faixa(raw: Any, codigo: Any) -> Faixa | None:
    if raw is None:
        return None
    try:
        # str() antes de Decimal evita herdar o erro de representação do float do YAML.
        faixa = Faixa(Decimal(str(raw["min"])), Decimal(str(raw["max"])))
    except (TypeError, KeyError, InvalidOperation) as exc:
        raise ConfigError(f"`faixa` da série {codigo} deve ser {{min: N, max: N}}") from exc
    if faixa.minimo >= faixa.maximo:
        raise ConfigError(f"`faixa` da série {codigo}: min deve ser menor que max")
    return faixa


def _parse_serie(raw: dict[str, Any], carga_inicial: date) -> SerieConfig:
    missing = {"codigo", "nome", "periodicidade", "unidade"} - raw.keys()
    if missing:
        raise ConfigError(f"série sem os campos {sorted(missing)}: {raw}")
    if raw["periodicidade"] not in PERIODICIDADES:
        raise ConfigError(
            f"periodicidade inválida na série {raw['codigo']}: {raw['periodicidade']}"
        )
    inicio = raw.get("inicio", carga_inicial)
    if not isinstance(inicio, date):
        raise ConfigError(f"`inicio` da série {raw['codigo']} deve ser uma data AAAA-MM-DD")
    return SerieConfig(
        codigo=int(raw["codigo"]),
        nome=str(raw["nome"]),
        periodicidade=raw["periodicidade"],
        unidade=str(raw["unidade"]),
        inicio=inicio,
        faixa=_parse_faixa(raw.get("faixa"), raw["codigo"]),
    )


def load_series(path: Path | None = None) -> list[SerieConfig]:
    """Lê as séries do YAML (caminho padrão em `SERIES_CONFIG_PATH`)."""
    path = path or Path(os.environ.get("SERIES_CONFIG_PATH", DEFAULT_CONFIG_PATH))
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    carga_inicial = document.get("carga_inicial")
    if not isinstance(carga_inicial, date):
        raise ConfigError("`carga_inicial` deve ser uma data AAAA-MM-DD")
    raw_series = document.get("series") or []
    if not raw_series:
        raise ConfigError("nenhuma série configurada")

    series = [_parse_serie(raw, carga_inicial) for raw in raw_series]
    codigos = [s.codigo for s in series]
    if len(codigos) != len(set(codigos)):
        raise ConfigError(f"código de série repetido: {codigos}")
    return series
