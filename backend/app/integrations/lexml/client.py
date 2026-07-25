"""Cliente LexML (Fase 93) — busca de legislação via SRU/CQL, fail-soft.

LexML Brasil expõe uma API SRU pública (Search/Retrieval via URL, padrão
Library of Congress; consulta via CQL, resposta em XML). Documentação oficial
e o wrapper de terceiros `netoferraz/py-lexml-acervo` confirmam o formato
geral (operation=searchRetrieve, query=<CQL>, resposta com numberOfRecords/
title/urn) — mas o schema exato não é verificável neste ambiente (egress
bloqueado pra lexml.gov.br no sandbox). Cliente tolerante/fail-soft, mesma
postura das fontes credenciadas (PDPJ/Escavador/Judit/Jusbrasil): parsing
best-effort por tag local (ignora namespace), circuit breaker, e `None`
(não erro) sempre que a resposta não puder ser confirmada.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

import httpx
import structlog

from app.integrations.fontes.circuit_breaker import CircuitBreaker

log = structlog.get_logger()

LEXML_SRU_URL = "https://www.lexml.gov.br/busca/SRU"
_TIMEOUT = 15.0
_breaker = CircuitBreaker(name="lexml")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parsear_resposta(xml_text: str) -> dict | None:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    num_records: str | None = None
    titulo: str | None = None
    urn: str | None = None
    for el in root.iter():
        tag = _local(el.tag)
        if tag == "numberOfRecords" and el.text and num_records is None:
            num_records = el.text.strip()
        elif tag == "title" and el.text and titulo is None:
            titulo = el.text.strip()
        elif tag == "urn" and el.text and urn is None:
            urn = el.text.strip()

    if num_records is None or not num_records.isdigit():
        return None
    return {"encontrado": int(num_records) > 0, "titulo": titulo, "urn": urn}


async def buscar_lei(referencia: str) -> dict | None:
    """Busca uma referência de lei normalizada (ex.: "8078/1990") no LexML.

    Devolve `{"encontrado": bool, "titulo": str|None, "urn": str|None}` em
    caso de resposta parseável, ou `None` se não foi possível verificar
    (rede fora, circuito aberto, XML não parseável) — o chamador trata
    `None` como "não verificável", distinto de "não encontrado".
    """
    async def _f():
        params = {
            "operation": "searchRetrieve",
            "version": "1.1",
            "query": referencia,
            "maximumRecords": "1",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(LEXML_SRU_URL, params=params)
            if resp.status_code != 200:
                log.warning("lexml_http", status=resp.status_code)
                raise RuntimeError(f"lexml status {resp.status_code}")
            return resp.text

    xml_text = await _breaker.run(_f, default=None)
    if xml_text is None:
        return None
    return _parsear_resposta(xml_text)
