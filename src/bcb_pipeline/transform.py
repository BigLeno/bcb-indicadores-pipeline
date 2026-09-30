"""Conversão do payload da API SGS em observações tipadas."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

_DATA_BR = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


class ParseError(ValueError):
    """Registro do payload que não pôde ser convertido."""


@dataclass(frozen=True)
class Observacao:
    """Um ponto da série: data e valor exato."""

    data: date
    valor: Decimal


@dataclass
class ParseResult:
    """Observações válidas e registros descartados, com o motivo."""

    observacoes: list[Observacao] = field(default_factory=list)
    descartados: list[tuple[dict[str, Any], str]] = field(default_factory=list)


def parse_data(texto: str) -> date:
    """Converte `dd/MM/aaaa` em `date`."""
    match = _DATA_BR.match(texto.strip())
    if match is None:
        raise ParseError(f"data fora do formato dd/MM/aaaa: {texto!r}")
    dia, mes, ano = (int(parte) for parte in match.groups())
    try:
        return date(ano, mes, dia)
    except ValueError as exc:
        raise ParseError(f"data inexistente: {texto!r}") from exc


def parse_valor(texto: str) -> Decimal:
    """Converte o valor em `Decimal`, aceitando ponto ou vírgula decimal.

    O JSON da API usa ponto (`"5.2204"`); o CSV usa vírgula (`"5,2204"`). Com vírgula,
    pontos são tratados como separador de milhar (`"1.234,56"`).
    """
    limpo = texto.strip()
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(limpo)
    except InvalidOperation as exc:
        raise ParseError(f"valor não numérico: {texto!r}") from exc
    if not valor.is_finite():
        raise ParseError(f"valor não finito: {texto!r}")
    return valor


def parse_payload(payload: Iterable[dict[str, Any]]) -> ParseResult:
    """Converte os registros `{"data", "valor"}`. Registros inválidos são descartados."""
    result = ParseResult()
    for registro in payload:
        try:
            data, valor = registro["data"], registro["valor"]
            if data is None or valor is None or str(valor).strip() == "":
                raise ParseError("data ou valor vazio")
            result.observacoes.append(Observacao(parse_data(str(data)), parse_valor(str(valor))))
        except (KeyError, ParseError) as exc:
            result.descartados.append((registro, str(exc)))
    return result


def deduplicar(observacoes: Iterable[Observacao]) -> list[Observacao]:
    """Uma observação por data; em caso de repetição, vale a última (a mais recente)."""
    por_data = {obs.data: obs for obs in observacoes}
    return [por_data[d] for d in sorted(por_data)]


def _somar_anos(dia: date, anos: int) -> date:
    try:
        return dia.replace(year=dia.year + anos)
    except ValueError:  # 29/02 num ano não bissexto
        return dia.replace(year=dia.year + anos, day=28)


def janelas(inicio: date, fim: date, anos: int) -> list[tuple[date, date]]:
    """Divide [inicio, fim] em janelas contíguas de no máximo `anos` anos, inclusivas."""
    if anos < 1:
        raise ValueError("o tamanho da janela deve ser de pelo menos 1 ano")
    resultado: list[tuple[date, date]] = []
    atual = inicio
    while atual <= fim:
        limite = min(_somar_anos(atual, anos) - timedelta(days=1), fim)
        resultado.append((atual, limite))
        atual = limite + timedelta(days=1)
    return resultado
