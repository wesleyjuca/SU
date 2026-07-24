"""Contrato base das fontes processuais (Fase 73).

`Capability` = o que uma fonte sabe fazer. `ProcessoDescoberto` = resultado
normalizado da descoberta por OAB. `FonteProcessual` = ABC com defaults
fail-soft: um método não suportado retorna vazio (nunca levanta), então o
chamador pode iterar fontes sem checar capability — embora `suporta()`/
`capabilities` permitam filtrar antes.
"""
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Só para type hints — evita puxar sqlalchemy/structlog no import do módulo.
    from app.services.movements_import import MovimentoEntrada


class Capability(str, Enum):
    """O que uma fonte consegue fornecer."""
    DESCOBRIR_OAB = "descobrir_oab"   # listar processos a partir de uma OAB
    DETALHAR = "detalhar"             # metadados de um processo pelo número
    MOVIMENTOS = "movimentos"         # andamentos de um processo
    PARTES = "partes"                 # partes/advogados (só fontes credenciadas)


@dataclass
class ProcessoDescoberto:
    """Processo encontrado numa descoberta por OAB (normalizado, agnóstico à fonte)."""
    numero_cnj: str | None            # só dígitos, para casamento
    tribunal: str | None = None
    uf: str | None = None
    fonte: str = ""
    raw: Any = None                   # objeto bruto da fonte (ex: Comunicacao)


class FonteProcessual(ABC):
    """Conector uniforme de dados processuais.

    Cada subclasse define `nome`, `capabilities` e sobrescreve apenas os métodos
    que suporta. Os defaults retornam vazio (degradação graciosa) — nunca
    levantam, para que orquestradores possam varrer várias fontes sem tratar
    exceções de capability."""

    nome: str = "base"
    capabilities: set[Capability] = set()

    def suporta(self, cap: Capability) -> bool:
        return cap in self.capabilities

    async def descobrir_por_oab(
        self,
        oab_numero: str,
        oab_uf: str,
        data_inicio: date,
        data_fim: date,
        **kwargs: Any,
    ) -> list[ProcessoDescoberto]:
        """Lista processos vinculados a uma OAB no período. Default: []."""
        return []

    async def detalhar(self, numero_cnj: str, tribunal: str | None = None) -> dict | None:
        """Metadados públicos de um processo pelo número. Default: None."""
        return None

    async def movimentos(
        self,
        numero_cnj: str,
        tribunal: str | None = None,
        since: datetime | None = None,
    ) -> "list[MovimentoEntrada]":
        """Andamentos do processo (opcionalmente desde `since`). Default: []."""
        return []

    async def partes(self, numero_cnj: str, tribunal: str | None = None) -> list[dict]:
        """Partes/advogados do processo (só fontes credenciadas). Default: []."""
        return []
