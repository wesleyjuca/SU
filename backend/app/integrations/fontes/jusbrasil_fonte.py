"""Fonte credenciada Jusbrasil (Fase 88) — descoberta por OAB + detalhe + partes.

Agregador comercial: exige token (Bearer) do escritório, guardado cifrado no hub
(provider "jusbrasil"). Cobre descoberta por OAB, detalhe, partes e movimentos —
mesmo escopo do Escavador/Judit (Fase 80), 4ª fonte credenciada de partes.

Fail-soft (circuit breaker; erro → vazio) e tolerante a variações de schema. Os
endpoints usam defaults sensatos e a base é configurável (o schema real da API
não é validável neste ambiente — parsing permissivo e best-effort). Não
persiste nada; quem grava partes é partes_import.

Nota: `DESCOBRIR_OAB` é declarado (a API real do Jusbrasil tem esse recurso),
mas ainda não está ligado à descoberta ativa — mesmo estado do Escavador hoje
(`oab_capture.py` só chama `descobrir_por_oab` na fonte pública `comunica`).
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

JUSBRASIL_BASE_DEFAULT = "https://api.jusbrasil.com.br"
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


class JusbrasilFonte(FonteProcessual):
    nome = "jusbrasil"
    capabilities = {Capability.DESCOBRIR_OAB, Capability.DETALHAR, Capability.MOVIMENTOS, Capability.PARTES}

    def __init__(self, token: str, base_url: str | None = None) -> None:
        self._token = token
        self._base = (base_url or JUSBRASIL_BASE_DEFAULT).rstrip("/")
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
                    log.warning("jusbrasil_http", status=resp.status_code, path=path)
                    raise RuntimeError(f"jusbrasil status {resp.status_code}")
                return resp.json()
        return await self._breaker.run(_f, default=None)

    async def _processo(self, numero_cnj: str) -> dict | None:
        numero = re.sub(r"\D", "", numero_cnj or "")
        if not numero:
            return None
        data = await self._get(f"/api/v1/processos/{numero}")
        if isinstance(data, dict):
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
        data = await self._get("/api/v1/advogados/processos",
                               params={"oab_numero": num, "oab_uf": oab_uf.upper()})
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

    async def testar(self) -> tuple[bool, str]:
        """Sonda leve p/ validar a credencial (distingue 401/403)."""
        if not self._token:
            return (False, "sem token")
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self._base}/api/v1/processos/0", headers=self._headers())
        except Exception as exc:
            return (False, str(exc)[:120])
        if resp.status_code in (401, 403):
            return (False, f"credencial rejeitada (HTTP {resp.status_code})")
        if resp.status_code >= 500:
            return (False, f"fonte indisponível (HTTP {resp.status_code})")
        return (True, f"ok (HTTP {resp.status_code})")

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


async def para_tenant(db, tenant_id: Any) -> "JusbrasilFonte | None":
    """Fonte Jusbrasil do escritório, ou None se não houve opt-in (sem credencial)."""
    try:
        from app.services import integration_hub
        creds = await integration_hub.get_credentials(db, tenant_id, "jusbrasil")
    except Exception as exc:
        log.warning("jusbrasil_creds_lookup_failed", error=str(exc))
        return None
    if not creds or not creds.get("token"):
        return None
    return JusbrasilFonte(token=creds["token"], base_url=creds.get("base_url") or None)
