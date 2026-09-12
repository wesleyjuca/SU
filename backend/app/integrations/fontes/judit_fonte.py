"""Fonte credenciada Judit (Fase 80) — detalhe + partes + movimentos por número
+ descoberta por OAB (Fase pós-262).

Agregador comercial (judit.io): exige token do escritório, guardado cifrado no
hub (provider "judit"), enviado no header `api-key`. Fail-soft (circuit breaker)
e parsing tolerante — o schema real não é validável neste ambiente, então o
parsing é permissivo e a base é configurável. Não persiste nada.
"""
from __future__ import annotations

import asyncio
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

JUDIT_BASE_DEFAULT = "https://requests.prod.judit.io"
_TIMEOUT = 25.0

# Sentinela para distinguir "disjuntor aberto/erro real" de "consulta vazia" —
# mesmo padrão já usado em datajud_fonte.py/pdpj_fonte.py/escavador_fonte.py.
_FALHA = object()

# Fase pós-262 — a busca por OAB da Judit é ASSÍNCRONA (confirmado via
# docs.judit.io: `POST /requests` cria a busca e devolve um `request_id`;
# os resultados aparecem incrementalmente em `GET /responses?
# request_id=...`, sem prazo fixo pra "completar"). `descobrir_por_oab()`
# não pode travar a resposta HTTP síncrona de `POST /tenant/oabs/capturar`
# por muito tempo — poll curto e limitado, devolve o que já estiver
# disponível dentro da janela (best-effort, não espera a busca terminar).
_OAB_POLL_TENTATIVAS = 4
_OAB_POLL_INTERVALO_S = 1.5


def _extrai_lista(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("page_data", "data", "responses", "results", "content"):
            v = data.get(k)
            if isinstance(v, list):
                return v
    return []


def _extrai_cnj(item) -> str | None:
    """Um item de resposta pode ser o processo em si, ou embrulhar em
    `response_data`/`lawsuit`/`response` — schema exato não confirmável
    neste sandbox (egress bloqueado pra requests.prod.judit.io), parsing
    tolerante como o resto do arquivo."""
    if not isinstance(item, dict):
        return None
    alvo = item
    for wrapper in ("response_data", "lawsuit", "response"):
        v = item.get(wrapper)
        if isinstance(v, dict):
            alvo = v
            break
    bruto = (alvo.get("code") or alvo.get("numero_cnj") or alvo.get("cnj")
             or alvo.get("lawsuit_cnj") or alvo.get("numeroProcesso") or alvo.get("numero"))
    cnj = re.sub(r"\D", "", str(bruto or ""))
    return cnj or None


class JuditFonte(FonteProcessual):
    nome = "judit"
    capabilities = {Capability.DETALHAR, Capability.MOVIMENTOS, Capability.PARTES,
                     Capability.DESCOBRIR_OAB}

    def __init__(self, token: str, base_url: str | None = None) -> None:
        self._token = token
        self._base = (base_url or JUDIT_BASE_DEFAULT).rstrip("/")
        self._breaker = CircuitBreaker(name=self.nome)

    async def _processo(self, numero_cnj: str, *, sinalizar_falha: bool = False):
        # `sinalizar_falha=True` devolve o sentinela `_FALHA` (não `None`)
        # quando o disjuntor está aberto/a chamada falhou de verdade —
        # `partes()` traduz isso pro chamador final; achado da rodada
        # pós-166a43c (mesma classe já corrigida pro DataJud/PDPJ/Escavador).
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
        return await self._breaker.run(_f, default=_FALHA if sinalizar_falha else None)

    async def testar(self) -> tuple[bool, str]:
        """Sonda leve p/ validar a credencial (distingue 401/403)."""
        if not self._token:
            return (False, "sem token")
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self._base}/responses",
                                        headers={"api-key": self._token, "Accept": "application/json"},
                                        params={"search_key": "0"})
        except Exception as exc:
            return (False, str(exc)[:120])
        if resp.status_code in (401, 403):
            return (False, f"credencial rejeitada (HTTP {resp.status_code})")
        if resp.status_code >= 500:
            return (False, f"fonte indisponível (HTTP {resp.status_code})")
        return (True, f"ok (HTTP {resp.status_code})")

    async def detalhar(self, numero_cnj: str, tribunal: str | None = None) -> dict | None:
        return await self._processo(numero_cnj)

    async def partes(
        self, numero_cnj: str, tribunal: str | None = None, *, sinalizar_falha: bool = False,
    ) -> "list[ParteEntrada] | None":
        from app.integrations.fontes._partes import extrair_partes
        dados = await self._processo(numero_cnj, sinalizar_falha=sinalizar_falha)
        if sinalizar_falha and dados is _FALHA:
            return None
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

    async def descobrir_por_oab(
        self, oab_numero: str, oab_uf: str, data_inicio, data_fim, **kwargs: Any,
    ) -> list[ProcessoDescoberto]:
        """Fase pós-262 — nova. `search_key` no formato `"{UF}{numero}"`
        (ex.: `"SP123456"`), confirmado via docs.judit.io. Poll curto (ver
        `_OAB_POLL_TENTATIVAS`/`_OAB_POLL_INTERVALO_S`) — nunca espera a
        busca "completar" de verdade, só dá uma janela curta pro que já
        estiver disponível. Fail-soft completo: qualquer erro/timeout
        devolve `[]`, nunca propaga."""
        if not self._token:
            return []
        num = re.sub(r"\D", "", oab_numero or "")
        if not num or not oab_uf:
            return []
        search_key = f"{oab_uf.upper()}{num}"

        async def _f():
            headers = {"api-key": self._token, "Accept": "application/json",
                       "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._base}/requests", headers=headers,
                    json={"search": {"search_type": "oab", "search_key": search_key}},
                )
                if resp.status_code not in (200, 201):
                    log.warning("judit_oab_request_http", status=resp.status_code, oab=search_key)
                    raise RuntimeError(f"judit status {resp.status_code}")
                request_id = (resp.json() or {}).get("request_id")
                if not request_id:
                    return []

                itens: list = []
                for _ in range(_OAB_POLL_TENTATIVAS):
                    await asyncio.sleep(_OAB_POLL_INTERVALO_S)
                    resp2 = await client.get(
                        f"{self._base}/responses", headers=headers,
                        params={"request_id": request_id},
                    )
                    if resp2.status_code != 200:
                        continue
                    encontrados = _extrai_lista(resp2.json())
                    if encontrados:
                        itens = encontrados
                        break
                return itens

        dados = await self._breaker.run(_f, default=None)
        if not dados:
            return []
        out: list[ProcessoDescoberto] = []
        vistos: set[str] = set()
        for it in dados:
            cnj = _extrai_cnj(it)
            if not cnj or cnj in vistos:
                continue
            vistos.add(cnj)
            out.append(ProcessoDescoberto(
                numero_cnj=cnj, tribunal=None, uf=oab_uf.upper(), fonte=self.nome, raw=it,
            ))
        return out


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
