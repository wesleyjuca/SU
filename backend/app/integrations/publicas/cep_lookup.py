"""Fase 217 — consulta de endereço por CEP via BrasilAPI. Deliberadamente
separado de `integrations/serpro/` (pasta reservada a canais governamentais
oficiais/comerciais) — a BrasilAPI é uma API pública **gratuita e de
terceiros**, não um canal oficial de governo: agrega Correios/ViaCEP/WideNet
com fallback automático entre as três, sem exigir credencial. O canal
oficial (contrato comercial direto com os Correios, ou a API CEP do Conecta
gov.br) segue restrito a convênio/contrato — não avaliado nesta fase.
Nunca apresentar isso como "fonte governamental" na UI."""
from __future__ import annotations

import re

import httpx
import structlog

from app.integrations.fontes.circuit_breaker import CircuitBreaker

log = structlog.get_logger()

_TIMEOUT = 10.0
_BASE_URL = "https://brasilapi.com.br/api/cep/v2"
_breaker = CircuitBreaker(name="brasilapi_cep")


async def consultar_cep(cep: str) -> dict | None:
    """Devolve `{logradouro, bairro, cidade, uf}` ou `None` — CEP inválido,
    não encontrado, ou serviço indisponível. Nunca levanta exceção."""
    numero = re.sub(r"\D", "", cep or "")
    if len(numero) != 8:
        return None

    async def _f():
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_BASE_URL}/{numero}")
            if resp.status_code != 200:
                log.warning("brasilapi_cep_http", status=resp.status_code)
                raise RuntimeError(f"BrasilAPI status {resp.status_code}")
            data = resp.json()
            return {
                "logradouro": data.get("street") or "",
                "bairro": data.get("neighborhood") or "",
                "cidade": data.get("city") or "",
                "uf": data.get("state") or "",
            }

    return await _breaker.run(_f, default=None)
