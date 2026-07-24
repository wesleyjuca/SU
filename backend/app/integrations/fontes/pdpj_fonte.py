"""Fonte credenciada PJe/PDPJ (Fase 75) — detalhe + PARTES + movimentos.

Diferente das fontes públicas (Comunica/DataJud), esta exige credencial do
escritório: um token SSO (Bearer) do CNJ Corporativo, guardado cifrado no hub de
integrações (provider "pdpj"). É a única fonte que expõe as PARTES do processo
(autor, réu, advogados) — a base pública do DataJud não as indexa.

Opt-in por tenant: `para_tenant(db, tenant_id)` devolve uma `PdpjFonte`
configurada só se o escritório conectou a credencial; caso contrário, None.

Tolerante a variações de schema (a resposta do PDPJ varia por tribunal/versão)
e fail-soft (circuit breaker; erro → vazio). Não escreve nada — quem persiste as
partes é `services/partes_import.importar_partes`.
"""
from __future__ import annotations

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

# Portal nacional do PDPJ (default quando o escritório não informa base própria).
PDPJ_BASE_DEFAULT = "https://portaldeservicos.pdpj.jus.br"
_TIMEOUT = 25.0


def parse_pdpj_partes(dados: dict) -> "list[ParteEntrada]":
    """Extrai partes + advogados da resposta do PDPJ (parser compartilhado)."""
    from app.integrations.fontes._partes import extrair_partes
    return extrair_partes(dados)


class PdpjFonte(FonteProcessual):
    nome = "pdpj"
    capabilities = {Capability.DETALHAR, Capability.MOVIMENTOS, Capability.PARTES}

    def __init__(self, token: str, base_url: str | None = None) -> None:
        self._token = token
        self._base = (base_url or PDPJ_BASE_DEFAULT).rstrip("/")
        self._breaker = CircuitBreaker(name=self.nome)

    async def _get_processo(self, numero_cnj: str) -> dict | None:
        """GET do processo no PDPJ (Bearer). Fail-soft sob o breaker."""
        if not self._token:
            return None
        import re
        numero = re.sub(r"\D", "", numero_cnj or "")
        if not numero:
            return None

        async def _f():
            url = f"{self._base}/api/v2/processos/{numero}"
            headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    log.warning("pdpj_http", status=resp.status_code, numero=numero)
                    raise RuntimeError(f"pdpj status {resp.status_code}")
                data = resp.json()
            # Algumas respostas embrulham em lista/'content'.
            if isinstance(data, list):
                return data[0] if data else None
            if isinstance(data, dict) and isinstance(data.get("content"), list):
                return data["content"][0] if data["content"] else None
            return data if isinstance(data, dict) else None

        return await self._breaker.run(_f, default=None)

    async def detalhar(self, numero_cnj: str, tribunal: str | None = None) -> dict | None:
        return await self._get_processo(numero_cnj)

    async def partes(self, numero_cnj: str, tribunal: str | None = None) -> "list[ParteEntrada]":
        dados = await self._get_processo(numero_cnj)
        if not dados:
            return []
        return parse_pdpj_partes(dados)

    async def movimentos(
        self,
        numero_cnj: str,
        tribunal: str | None = None,
        since: datetime | None = None,
    ) -> "list[MovimentoEntrada]":
        from app.services.movements_import import parse_datajud_movimentos
        dados = await self._get_processo(numero_cnj)
        if not dados:
            return []
        # O PDPJ usa o mesmo formato de movimentos do DataJud (nome/dataHora).
        movs = parse_datajud_movimentos(dados)
        if since:
            movs = [m for m in movs if m.data and m.data >= since]
        return movs


async def para_tenant(db, tenant_id: Any) -> "PdpjFonte | None":
    """Fonte PDPJ configurada para o escritório, ou None se não houve opt-in
    (sem credencial conectada no hub). Espelha o padrão dos demais provedores."""
    try:
        from app.services import integration_hub
        creds = await integration_hub.get_credentials(db, tenant_id, "pdpj")
    except Exception as exc:
        log.warning("pdpj_creds_lookup_failed", error=str(exc))
        return None
    if not creds or not creds.get("sso_token"):
        return None
    return PdpjFonte(token=creds["sso_token"], base_url=creds.get("base_url") or None)
