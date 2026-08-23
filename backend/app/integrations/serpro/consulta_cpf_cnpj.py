"""Fase 217 — Consulta CPF/CNPJ via Loja SERPRO (canal comercial self-service,
`loja.serpro.gov.br`, fora do Conecta gov.br gratuito — que é restrito a
convênio entre órgãos públicos). Único item da auditoria de APIs
governamentais (ver artefato "Integração Conecta gov.br") com valor de
negócio confirmado (`Client.cpf`/`cnpj` nunca são validados hoje) *e*
caminho de acesso comercial viável pra uma empresa privada.

REST puro via httpx, sem SDK — mesmo padrão de todo `integrations/`
(inclusive `_vertex_access_token`, Fase 195, que também troca credencial
por token OAuth2 cacheado). Fail-soft via `CircuitBreaker`: qualquer erro
(timeout, 401, 429, circuito aberto) devolve `None`, nunca propaga
exceção — a validação de documento nunca pode bloquear o cadastro de um
cliente."""
from __future__ import annotations

import base64
import re
import time

import httpx
import structlog

from app.config import settings
from app.integrations.fontes.circuit_breaker import CircuitBreaker

log = structlog.get_logger()

_TIMEOUT = 15.0
_breaker = CircuitBreaker(name="serpro")

# Cache de token local a este módulo — concern próprio, não reaproveita o
# `_client_cache` de `llm_client.py` (que é de credenciais de LLM por
# usuário/BYOK, natureza diferente desta credencial única e plataforma-wide).
_token_cache: dict[str, tuple[str, float]] = {}


def _configurado() -> bool:
    return bool(settings.SERPRO_API_CONSUMER_KEY and settings.SERPRO_API_CONSUMER_SECRET)


async def _get_token() -> str | None:
    cached = _token_cache.get("token")
    if cached and cached[1] > time.time() + 30:
        return cached[0]

    basic = base64.b64encode(
        f"{settings.SERPRO_API_CONSUMER_KEY}:{settings.SERPRO_API_CONSUMER_SECRET}".encode()
    ).decode()
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            settings.SERPRO_TOKEN_URL,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
        )
    if resp.status_code >= 400:
        log.warning("serpro_token_recusado", status=resp.status_code)
        raise RuntimeError(f"SERPRO recusou o token ({resp.status_code}): {resp.text[:200]}")
    data = resp.json()
    token = data["access_token"]
    _token_cache["token"] = (token, time.time() + data.get("expires_in", 3600))
    return token


async def _consultar(base_url: str, numero: str) -> dict | None:
    if not _configurado():
        return None

    async def _f():
        token = await _get_token()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{base_url}/{numero}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                log.warning("serpro_consulta_http", status=resp.status_code)
                raise RuntimeError(f"SERPRO status {resp.status_code}")
            return resp.json()

    return await _breaker.run(_f, default=None)


async def consultar_cpf(cpf: str) -> dict | None:
    """Devolve o payload bruto da SERPRO (nome, situação cadastral, etc.) ou
    `None` — quando não configurado, indisponível, ou circuito aberto."""
    numero = re.sub(r"\D", "", cpf or "")
    if len(numero) != 11:
        return None
    return await _consultar(settings.SERPRO_CPF_BASE_URL, numero)


async def consultar_cnpj(cnpj: str) -> dict | None:
    """Devolve o payload bruto da SERPRO (razão social, situação cadastral,
    QSA, etc.) ou `None` — quando não configurado, indisponível, ou circuito
    aberto."""
    numero = re.sub(r"\D", "", cnpj or "")
    if len(numero) != 14:
        return None
    return await _consultar(settings.SERPRO_CNPJ_BASE_URL, numero)
