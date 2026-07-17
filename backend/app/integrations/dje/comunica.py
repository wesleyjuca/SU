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


def _extrai_itens(data) -> list:
    """Extrai a lista de itens da resposta (formato varia por edição da API)."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("items") or data.get("content") or data.get("comunicacoes") or []
    return []


async def buscar_comunicacoes(
    oab_numero: str,
    oab_uf: str,
    data_inicio: date,
    data_fim: date,
    max_paginas: int = 1,
    itens_por_pagina: int = 50,
    stats: dict | None = None,
) -> list[Comunicacao]:
    """Consulta a Comunica por OAB e intervalo de disponibilização.

    `max_paginas` controla quantas páginas varrer (1 = comportamento antigo, p/ a
    varredura diária do DJe; a captura por OAB usa um valor maior). Para de paginar
    assim que uma página vem incompleta/vazia.

    `stats` (opcional) é preenchido para diagnóstico: `ok` (True se a fonte
    respondeu 200 ao menos uma vez), `requests` (nº de chamadas) e `error` (última
    exceção). Permite ao chamador distinguir "fonte inalcançável" de "0 no período".

    Retorna [] em qualquer falha (host inacessível no sandbox, timeout, formato
    inesperado). Em produção (Railway), roda de verdade.
    """
    numero = _digits(oab_numero)
    if not numero or not oab_uf:
        return []

    out: list[Comunicacao] = []
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            for pagina in range(1, max(1, max_paginas) + 1):
                params = {
                    "numeroOab": numero,
                    "ufOab": oab_uf.upper(),
                    "dataDisponibilizacaoInicio": data_inicio.isoformat(),
                    "dataDisponibilizacaoFim": data_fim.isoformat(),
                    "itensPorPagina": itens_por_pagina,
                    "pagina": pagina,
                }
                resp = await client.get(COMUNICA_URL, params=params)
                if stats is not None:
                    stats["requests"] = stats.get("requests", 0) + 1
                if resp.status_code != 200:
                    log.warning("comunica_http", status=resp.status_code, oab=numero, uf=oab_uf, pagina=pagina)
                    break
                if stats is not None:
                    stats["ok"] = True
                itens = _extrai_itens(resp.json())
                for it in itens:
                    if isinstance(it, dict):
                        try:
                            out.append(_normalize(it))
                        except Exception:
                            continue
                # Página incompleta → não há próxima.
                if len(itens) < itens_por_pagina:
                    break
    except Exception as exc:
        if stats is not None:
            stats["error"] = str(exc)
        log.warning("comunica_falhou", error=str(exc), oab=numero, uf=oab_uf)
        return out

    log.info("comunica_ok", oab=numero, uf=oab_uf, encontradas=len(out))
    return out
