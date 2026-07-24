"""Fonte de detalhe + movimentos via DataJud público do CNJ (Fase 73).

Envolve `integrations/tribunais/cnj.py::CNJDataJudClient`. Fornece `detalhar`
(metadados) e `movimentos` (andamentos normalizados em `MovimentoEntrada`,
reusando `parse_datajud_movimentos`). NÃO fornece partes — a API pública do
DataJud não as expõe (isso fica para a fonte PJe/PDPJ credenciada, Fase 75).
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from app.integrations.fontes.base import Capability, FonteProcessual
from app.integrations.fontes.circuit_breaker import CircuitBreaker

if TYPE_CHECKING:
    from app.services.movements_import import MovimentoEntrada


class DataJudFonte(FonteProcessual):
    nome = "datajud"
    capabilities = {Capability.DETALHAR, Capability.MOVIMENTOS}

    def __init__(self) -> None:
        self._breaker = CircuitBreaker(name=self.nome)

    def _client(self, tribunal: str | None):
        from app.integrations.tribunais.cnj import CNJDataJudClient
        return CNJDataJudClient(tribunal=tribunal or "TJCE")

    async def detalhar(self, numero_cnj: str, tribunal: str | None = None) -> dict | None:
        async def _f():
            return await self._client(tribunal).fetch_processo(numero_cnj, tribunal=tribunal)
        return await self._breaker.run(_f, default=None)

    async def movimentos(
        self,
        numero_cnj: str,
        tribunal: str | None = None,
        since: datetime | None = None,
    ) -> "list[MovimentoEntrada]":
        async def _f():
            from app.services.movements_import import parse_datajud_movimentos
            dados = await self._client(tribunal).fetch_processo(numero_cnj, tribunal=tribunal)
            if not dados:
                return []
            movs = parse_datajud_movimentos(dados)
            if since:
                movs = [m for m in movs if m.data and m.data >= since]
            return movs
        return await self._breaker.run(_f, default=[])
