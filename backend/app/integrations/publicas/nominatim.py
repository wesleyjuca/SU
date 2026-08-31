"""Fase 257.4 — geocodificação por endereço estruturado (rua + número +
cidade + UF) via Nominatim, o geocoder oficial do projeto OpenStreetMap
(gratuito, sem credencial) — mesma família "fonte pública gratuita, sem
custo/credencial nova" já usada em `cep_lookup.py` (BrasilAPI) e no tile
server do `/mapa` (OSM). Refinamento OPCIONAL de precisão sobre o caminho
já existente (BrasilAPI, centro do CEP/quadra): só tentado quando o
cliente informa o número do imóvel (campo novo, `Endereco.numero`), e
sempre com fallback fail-soft pro caminho de CEP se não encontrar nada ou
o serviço estiver fora do ar — nunca faz o cadastro depender dele.

Respeita a política de uso do Nominatim
(https://operations.osmfoundation.org/policies/nominatim/): identificação
via User-Agent próprio (nunca o default de uma lib HTTP), volume baixo por
desenho (1 chamada por save de cliente, nunca em lote — a correção em
massa da Fase 255 continua só na BrasilAPI, evitando estourar o limite de
1 req/s da política num lote de até 200 clientes)."""
from __future__ import annotations

import httpx
import structlog

from app.integrations.fontes.circuit_breaker import CircuitBreaker
from app.integrations.publicas.cep_lookup import coordenada_valida

log = structlog.get_logger()

_TIMEOUT = 10.0
_BASE_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "AFJ-Core-Legal-SaaS/1.0 (geocodificacao de cadastro de cliente; sem contato publico)"
_breaker = CircuitBreaker(name="nominatim")


async def geocodificar_endereco_completo(
    logradouro: str, numero: str, cidade: str, uf: str,
) -> tuple[float, float] | None:
    """Devolve `(latitude, longitude)` pro endereço estruturado informado,
    ou `None` se não encontrar resultado ou o serviço estiver indisponível.
    Nunca levanta exceção — mesmo contrato de `cep_lookup.consultar_cep`."""
    if not logradouro or not numero or not cidade or not uf:
        return None

    async def _f():
        params = {
            "street": f"{numero} {logradouro}",
            "city": cidade,
            "state": uf,
            "country": "Brazil",
            "format": "jsonv2",
            "limit": 1,
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_BASE_URL, params=params, headers={"User-Agent": _USER_AGENT})
            if resp.status_code != 200:
                log.warning("nominatim_http", status=resp.status_code)
                raise RuntimeError(f"Nominatim status {resp.status_code}")
            data = resp.json()
            if not data:
                return None
            try:
                lat = float(data[0]["lat"])
                lng = float(data[0]["lon"])
            except (KeyError, TypeError, ValueError, IndexError):
                return None
            if not coordenada_valida(lat, lng):
                log.warning("nominatim_coordenada_invalida", latitude=lat, longitude=lng)
                return None
            return (lat, lng)

    return await _breaker.run(_f, default=None)
