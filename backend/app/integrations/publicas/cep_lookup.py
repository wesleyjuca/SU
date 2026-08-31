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


def _extrair_coordenadas(data: dict) -> tuple[float | None, float | None]:
    """Fase 230 — a BrasilAPI v2 devolve (quando a fonte subjacente,
    viacep/correios/widenet, tiver o dado) um bloco `location.coordinates.
    {latitude,longitude}` — precisão de CEP/quadra, não do número exato do
    endereço. `location` pode vir ausente ou `{}` quando nenhuma fonte tem
    a coordenada; nunca levanta exceção, só devolve (None, None) nesse caso.

    Fase 253 — ponto único de validação de sanidade da coordenada (todo
    consumidor de `consultar_cep()` — Cliente, Tenant, preview do form —
    ganha a proteção de graça): rejeita fora da faixa geográfica válida
    (-90..90/-180..180) e `(0, 0)` (sentinela comum de "não encontrado"
    em geocodificadores, nunca uma coordenada real de CEP brasileiro)."""
    coords = ((data.get("location") or {}).get("coordinates")) or {}
    try:
        lat = float(coords["latitude"])
        lng = float(coords["longitude"])
    except (KeyError, TypeError, ValueError):
        return None, None
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lng <= 180.0):
        log.warning("brasilapi_cep_coordenada_fora_de_faixa", latitude=lat, longitude=lng)
        return None, None
    if lat == 0.0 and lng == 0.0:
        log.warning("brasilapi_cep_coordenada_null_island")
        return None, None
    return lat, lng


async def consultar_cep(cep: str) -> dict | None:
    """Devolve `{logradouro, bairro, cidade, uf, latitude, longitude}` ou
    `None` — CEP inválido, não encontrado, ou serviço indisponível. Nunca
    levanta exceção. `latitude`/`longitude` vêm `None` quando a BrasilAPI
    não tiver essa coordenada pro CEP consultado (comum, best-effort)."""
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
            latitude, longitude = _extrair_coordenadas(data)
            return {
                "logradouro": data.get("street") or "",
                "bairro": data.get("neighborhood") or "",
                "cidade": data.get("city") or "",
                "uf": data.get("state") or "",
                "latitude": latitude,
                "longitude": longitude,
            }

    return await _breaker.run(_f, default=None)
