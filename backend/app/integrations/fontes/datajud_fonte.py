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

# Sentinela para distinguir "consulta falhou" de "consulta vazia".
_FALHA = object()

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

    @staticmethod
    async def _fechar(cli) -> None:
        fechar = getattr(cli, "close", None)
        if fechar:
            try:
                await fechar()
            except Exception:
                pass

    async def detalhar(
        self, numero_cnj: str, tribunal: str | None = None, *, sinalizar_falha: bool = False,
    ) -> dict | None:
        # Fase pós-260.10 (achado de auditoria, mesmo padrão já usado em
        # fetch_movements_datajud abaixo) — `sinalizar_falha` deixa disponível
        # a distinção entre "disjuntor aberto/consulta não aconteceu" e
        # "consultei e não achei nada" pra um futuro chamador que precise
        # dela. Hoje devolve `None` nos dois casos de qualquer forma (é o
        # contrato já documentado da função) — não muda comportamento pros 2
        # chamadores reais (`oab_capture.py`, `citacao_check.py`), nenhum
        # passa o parâmetro.
        async def _f():
            cli = self._client(tribunal)
            try:
                return await cli.fetch_processo(numero_cnj, tribunal=tribunal)
            finally:
                await self._fechar(cli)
        resultado = await self._breaker.run(_f, default=_FALHA if sinalizar_falha else None)
        return None if resultado is _FALHA else resultado

    async def movimentos(
        self,
        numero_cnj: str,
        tribunal: str | None = None,
        since: datetime | None = None,
        *,
        sinalizar_falha: bool = False,
    ) -> "list[MovimentoEntrada] | None":
        # Fase pós-260.10 (achado de auditoria, reproduzido ao vivo) —
        # `self._breaker.run(_f, default=[])` fazia "disjuntor aberto" e
        # "consultei e não havia andamento novo" virarem o mesmo `[]`,
        # indistinguível pro chamador — mesma classe de bug já corrigida só
        # pro Comunica/DJEN (ver `sinalizar_falha` em `fetch_movements_datajud`
        # abaixo). `movimentos()` não tem chamador em produção hoje (só
        # `fetch_movements_datajud` é usado, por `process_agent.py`) — o
        # parâmetro fica disponível pro padrão ficar consistente entre os 3
        # métodos, sem forçar um consumidor que não existe; default preserva
        # o comportamento fail-soft atual.
        async def _f():
            from app.services.movements_import import parse_datajud_movimentos
            cli = self._client(tribunal)
            try:
                dados = await cli.fetch_processo(numero_cnj, tribunal=tribunal)
            finally:
                await self._fechar(cli)
            if not dados:
                return []
            movs = parse_datajud_movimentos(dados)
            if since:
                movs = [m for m in movs if m.data and m.data >= since]
            return movs
        resultado = await self._breaker.run(_f, default=_FALHA if sinalizar_falha else [])
        return None if resultado is _FALHA else resultado

    async def fetch_movements_datajud(
        self,
        numero_cnj: str,
        tribunal: str | None = None,
        since: datetime | None = None,
        *,
        sinalizar_falha: bool = False,
    ) -> list | None:
        """Andamentos como `MovementData` (tipo/código + raw preservados) sob o
        breaker. Usado pelo polling do ProcessAgent, que consome MovementData
        diretamente — a `movimentos()` canônica devolve MovimentoEntrada (sem
        código/raw). `fetch_movements` usa `self.tribunal`, então o fixamos aqui."""
        async def _f():
            cli = self._client(tribunal)
            if tribunal:
                cli.tribunal = tribunal.upper()
            try:
                return await cli.fetch_movements(numero_cnj, since=since)
            finally:
                await self._fechar(cli)

        # `sinalizar_falha=True` devolve None quando a consulta NÃO aconteceu
        # (breaker aberto, rede fora, erro do DataJud), em vez de `[]`.
        # Sem isso, "consultei e não havia andamento novo" e "não consegui
        # consultar" são o mesmo valor — e o polling em lote registrava um
        # ciclo inteiro sem nenhuma consulta bem-sucedida como `status="OK",
        # errors: 0`. O default (`False`) preserva o comportamento fail-soft
        # de todos os outros chamadores.
        resultado = await self._breaker.run(_f, default=_FALHA if sinalizar_falha else [])
        if resultado is _FALHA:
            return None
        return resultado
