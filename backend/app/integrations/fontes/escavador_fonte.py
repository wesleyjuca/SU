"""Fonte credenciada Escavador (Fase 80) — descoberta por OAB + detalhe + partes.

Agregador comercial: exige token (Bearer) do escritório, guardado cifrado no hub
(provider "escavador"). Cobre descoberta por OAB, detalhe, partes e movimentos.

Como as fontes PDPJ/DataJud, é fail-soft (circuit breaker; erro → vazio) e
tolerante a variações de schema. Os endpoints usam defaults sensatos e a base é
configurável (o schema real da API não é validável neste ambiente — o parsing é
permissivo e best-effort). Não persiste nada; quem grava partes é partes_import.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from app.integrations.fontes.base import Capability, FonteProcessual, ProcessoDescoberto
from app.integrations.fontes.circuit_breaker import CircuitBreaker

if TYPE_CHECKING:
    from app.services.movements_import import MovimentoEntrada
    from app.services.partes_import import ParteEntrada

log = structlog.get_logger()

ESCAVADOR_BASE_DEFAULT = "https://api.escavador.com"
_TIMEOUT = 25.0


def _extrai_lista(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("items", "data", "processos", "content", "results"):
            v = data.get(k)
            if isinstance(v, list):
                return v
    return []


class EscavadorFonte(FonteProcessual):
    nome = "escavador"
    capabilities = {Capability.DESCOBRIR_OAB, Capability.DETALHAR, Capability.MOVIMENTOS, Capability.PARTES}

    def __init__(self, token: str, base_url: str | None = None) -> None:
        self._token = token
        self._base = (base_url or ESCAVADOR_BASE_DEFAULT).rstrip("/")
        self._breaker = CircuitBreaker(name=self.nome)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    async def _get(self, path: str, params: dict | None = None):
        if not self._token:
            return None

        async def _f():
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(f"{self._base}{path}", headers=self._headers(), params=params or {})
                if resp.status_code != 200:
                    log.warning("escavador_http", status=resp.status_code, path=path)
                    raise RuntimeError(f"escavador status {resp.status_code}")
                return resp.json()
        return await self._breaker.run(_f, default=None)

    async def _processo(self, numero_cnj: str) -> dict | None:
        numero = re.sub(r"\D", "", numero_cnj or "")
        if not numero:
            return None
        data = await self._get(f"/api/v2/processos/numero_cnj/{numero}")
        if isinstance(data, dict):
            # algumas respostas embrulham em {"processo": {...}}
            if isinstance(data.get("processo"), dict):
                return data["processo"]
            return data
        return None

    async def descobrir_por_oab(
        self, oab_numero: str, oab_uf: str, data_inicio, data_fim, **kwargs: Any,
    ) -> list[ProcessoDescoberto]:
        num = re.sub(r"\D", "", oab_numero or "")
        if not num or not oab_uf:
            return []
        data = await self._get("/api/v2/advogados/processos",
                               params={"oab_numero": num, "oab_estado": oab_uf.upper()})
        out: list[ProcessoDescoberto] = []
        vistos: set[str] = set()
        for it in _extrai_lista(data):
            if not isinstance(it, dict):
                continue
            bruto = it.get("numero_cnj") or it.get("numeroProcesso") or it.get("numero")
            cnj = re.sub(r"\D", "", str(bruto or ""))
            if not cnj or cnj in vistos:
                continue
            vistos.add(cnj)
            out.append(ProcessoDescoberto(
                numero_cnj=cnj, tribunal=(it.get("tribunal") or None),
                uf=oab_uf.upper(), fonte=self.nome, raw=it,
            ))
        return out

    async def detalhar(self, numero_cnj: str, tribunal: str | None = None) -> dict | None:
        return await self._processo(numero_cnj)

    async def partes(self, numero_cnj: str, tribunal: str | None = None) -> "list[ParteEntrada]":
        from app.integrations.fontes._partes import extrair_partes
        dados = await self._processo(numero_cnj)
        return extrair_partes(dados) if dados else []

    async def movimentos(
        self, numero_cnj: str, tribunal: str | None = None, since: datetime | None = None,
    ) -> "list[MovimentoEntrada]":
        from app.services.movements_import import parse_datajud_movimentos
        dados = await self._processo(numero_cnj)
        if not dados:
            return []
        movs = parse_datajud_movimentos(dados)
        if since:
            movs = [m for m in movs if m.data and m.data >= since]
        return movs


async def para_tenant(db, tenant_id: Any) -> "EscavadorFonte | None":
    """Fonte Escavador do escritório, ou None se não houve opt-in (sem credencial)."""
    try:
        from app.services import integration_hub
        creds = await integration_hub.get_credentials(db, tenant_id, "escavador")
    except Exception as exc:
        log.warning("escavador_creds_lookup_failed", error=str(exc))
        return None
    if not creds or not creds.get("token"):
        return None
    return EscavadorFonte(token=creds["token"], base_url=creds.get("base_url") or None)
