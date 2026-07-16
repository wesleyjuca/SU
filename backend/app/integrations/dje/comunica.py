"""Cliente da API Comunica/DJEN do PJe (Diário de Justiça Eletrônico Nacional).

Fonte PÚBLICA e gratuita (sem autenticação) de comunicações judiciais/intimações,
consultável por OAB. Documentação: https://comunicaapi.pje.jus.br/

À prova de falha: qualquer erro (rede, formato, host inacessível no sandbox)
retorna lista vazia — a varredura nunca derruba o worker.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import httpx
import structlog

log = structlog.get_logger()

COMUNICA_URL = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
_TIMEOUT = 20.0


@dataclass
class Comunicacao:
    """Intimação/publicação normalizada (campos da Comunica variam por edição)."""
    id_externo: str
    numero_cnj: str | None       # número do processo (só dígitos, p/ casamento)
    numero_cnj_fmt: str | None   # número com máscara (exibição)
    texto: str
    data_disponibilizacao: str | None   # ISO date
    tribunal: str | None
    tipo_comunicacao: str | None
    orgao: str | None
    link: str | None

    def hash_dedupe(self) -> str:
        base = f"{self.id_externo}|{self.numero_cnj}|{self.data_disponibilizacao}|{self.texto[:120]}"
        import hashlib
        return hashlib.sha256(base.encode("utf-8", "ignore")).hexdigest()


def _digits(v: str | None) -> str | None:
    if not v:
        return None
    d = re.sub(r"\D", "", v)
    return d or None


def _first(item: dict, *keys: str):
    for k in keys:
        if k in item and item[k] not in (None, ""):
            return item[k]
    return None


def _normalize(item: dict) -> Comunicacao:
    numero_fmt = _first(item, "numeroprocessocommascara", "numeroProcessoComMascara",
                        "numero_processo", "numeroProcesso", "numeroprocesso")
    return Comunicacao(
        id_externo=str(_first(item, "id", "hash", "numeroComunicacao", "numerocomunicacao") or ""),
        numero_cnj=_digits(numero_fmt),
        numero_cnj_fmt=str(numero_fmt) if numero_fmt else None,
        texto=str(_first(item, "texto", "textodocomunicado", "conteudo") or ""),
        data_disponibilizacao=(_first(item, "data_disponibilizacao", "dataDisponibilizacao",
                                      "datadisponibilizacao") or None),
        tribunal=_first(item, "siglaTribunal", "siglatribunal", "tribunal"),
        tipo_comunicacao=_first(item, "tipoComunicacao", "tipocomunicacao", "tipo"),
        orgao=_first(item, "nomeOrgao", "nomeorgao", "orgao"),
        link=_first(item, "link", "linkPje"),
    )


async def buscar_comunicacoes(
    oab_numero: str,
    oab_uf: str,
    data_inicio: date,
    data_fim: date,
) -> list[Comunicacao]:
    """Consulta a Comunica por OAB e intervalo de disponibilização.

    Retorna [] em qualquer falha (host inacessível no sandbox, timeout, formato
    inesperado). Em produção (Railway), roda de verdade.
    """
    numero = _digits(oab_numero)
    if not numero or not oab_uf:
        return []
    params = {
        "numeroOab": numero,
        "ufOab": oab_uf.upper(),
        "dataDisponibilizacaoInicio": data_inicio.isoformat(),
        "dataDisponibilizacaoFim": data_fim.isoformat(),
        "itensPorPagina": 50,
        "pagina": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(COMUNICA_URL, params=params)
            if resp.status_code != 200:
                log.warning("comunica_http", status=resp.status_code, oab=numero, uf=oab_uf)
                return []
            data = resp.json()
    except Exception as exc:
        log.warning("comunica_falhou", error=str(exc), oab=numero, uf=oab_uf)
        return []

    # A resposta pode vir como {"items": [...]} , {"content": [...]} ou lista pura.
    itens = data if isinstance(data, list) else (
        data.get("items") or data.get("content") or data.get("comunicacoes") or []
    )
    out: list[Comunicacao] = []
    for it in itens:
        if isinstance(it, dict):
            try:
                out.append(_normalize(it))
            except Exception:
                continue
    log.info("comunica_ok", oab=numero, uf=oab_uf, encontradas=len(out))
    return out
