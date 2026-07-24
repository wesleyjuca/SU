"""Fonte credenciada Judit (Fase 80) — detalhe + partes + movimentos por número.

Agregador comercial (judit.io): exige token do escritório, guardado cifrado no
hub (provider "judit"), enviado no header `api-key`. Fail-soft (circuit breaker)
e parsing tolerante — o schema real não é validável neste ambiente, então o
parsing é permissivo e a base é configurável. Não persiste nada.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from app.integrations.fontes.base import Capability, FonteProcessual
from app.integrations.fontes.circuit_breaker import CircuitBreaker

if TYPE_CHECKING:
    from app.services.movements_import import MovimentoEntrada
    from app.services.partes_import import ParteEntrada

log = structlog.get_logger()

JUDIT_BASE_DEFAULT = "https://requests.prod.judit.io"
_TIMEOUT = 25.0


class JuditFonte(FonteProcessual):
    nome = "judit"
    capabilities = {Capability.DETALHAR, Capability.MOVIMENTOS, Capability.PARTES}

    def __init__(self, token: str, base_url: str | None = None) -> None:
        self._token = token
        self._base = (base_url or JUDIT_BASE_DEFAULT).rstrip("/")
        self._breaker = CircuitBreaker(name=self.nome)

    async def _processo(self, numero_cnj: str) -> dict | None:
        if not self._token:
            return None
        numero = re.sub(r"\D", "", numero_cnj or "")
        if not numero:
            return None

        async def _f():
            headers = {"api-key": self._token, "Accept": "application/json"}
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(f"{self._base}/responses",
                                        headers=headers, params={"search_key": numero})
                if resp.status_code != 200:
                    log.warning("judit_http", status=resp.status_code, numero=numero)
                    raise RuntimeError(f"judit status {resp.status_code}")
                data = resp.json()
            # respostas costumam vir em {"page_data": [ {...} ]} ou lista
            if isinstance(data, dict):
                for k in ("page_data", "data", "responses", "content"):
                    v = data.get(k)
                    if isinstance(v, list) and v:
                        return v[0] if isinstance(v[0], dict) else None
                return data
            if isinstance(data, list) and data:
                return data[0] if isinstance(data[0], dict) else None
            return None
        return await self._breaker.run(_f, default=None)

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


async def para_tenant(db, tenant_id: Any) -> "JuditFonte | None":
    """Fonte Judit do escritório, ou None se não houve opt-in (sem credencial)."""
    try:
        from app.services import integration_hub
        creds = await integration_hub.get_credentials(db, tenant_id, "judit")
    except Exception as exc:
        log.warning("judit_creds_lookup_failed", error=str(exc))
        return None
    if not creds or not creds.get("token"):
        return None
    return JuditFonte(token=creds["token"], base_url=creds.get("base_url") or None)
