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


# ─── Fase 138.3 — descoberta em lote + texto integral (LexML → Planalto) ──────
#
# Nota honesta: o nome exato da tag que carrega a URL de publicação num
# <record> SRU do LexML (location? dc:identifier? url?) não é confirmável
# neste ambiente — aceitamos as 3 variantes plausíveis. Também não há
# paginação por data/cursor real: cada execução busca os N registros mais
# recentes por tipo de norma e a tabela de idempotência (JurisprudenciaIngerida)
# funciona como "cursor implícito", pulando o que já foi visto — mesma
# filosofia do cliente do STJ (Fase 138.1): processa só o lote mais recente,
# nunca um backfill histórico automático.

TIPOS_NORMA_SUPORTADOS = ("Lei", "Decreto")

_URL_TAGS = ("location", "url", "identifier")


def _parsear_registros(xml_text: str) -> list[dict]:
    """Extrai todos os <record> de uma resposta SRU multi-registro (ao
    contrário de `_parsear_resposta`, que só olha o 1º). Um <record>
    malformado ou sem `urn` é pulado, não derruba os demais. Nunca lança —
    XML não parseável devolve `[]`."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    registros: list[dict] = []
    for record_el in root.iter():
        if _local(record_el.tag) != "record":
            continue
        urn: str | None = None
        titulo: str | None = None
        url: str | None = None
        for el in record_el.iter():
            tag = _local(el.tag)
            if tag == "urn" and el.text and urn is None:
                urn = el.text.strip()
            elif tag == "title" and el.text and titulo is None:
                titulo = el.text.strip()
            elif tag in _URL_TAGS and el.text and url is None:
                candidato = el.text.strip()
                if candidato.startswith("http://") or candidato.startswith("https://"):
                    url = candidato
        if urn:  # sem URN não dá pra formar uma chave de idempotência estável
            registros.append({"urn": urn, "titulo": titulo, "url": url})
    return registros


async def buscar_lote_legislacao(tipo_norma: str, maximum_records: int = 50) -> list[dict]:
    """Busca um lote de normas federais recentes de um tipo (`"Lei"` ou
    `"Decreto"`) via SRU/CQL. Fail-soft: devolve `[]` (nunca lança) se a
    busca falhar em qualquer etapa (rede, circuito aberto, XML inválido)."""
    async def _f():
        params = {
            "operation": "searchRetrieve",
            "version": "1.1",
            "query": f"localidade=federal and tipoDocumento={tipo_norma}",
            "maximumRecords": str(maximum_records),
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(LEXML_SRU_URL, params=params)
            if resp.status_code != 200:
                log.warning("lexml_bulk_http", status=resp.status_code, tipo=tipo_norma)
                raise RuntimeError(f"lexml status {resp.status_code}")
            return resp.text

    xml_text = await _breaker.run(_f, default=None)
    if xml_text is None:
        return []
    return _parsear_registros(xml_text)


async def buscar_lote_legislacao_federal(maximum_records_por_tipo: int = 50) -> list[dict]:
    """Ponto de entrada usado pela task de sync: busca leis e decretos
    federais recentes, filtra registros sem URL de publicação resolvível
    (não tenta construir uma URL do Planalto na mão — risco de migração de
    portal, ver docstring do módulo) e devolve a lista combinada. Cada item:
    `{"urn", "titulo", "url", "tipo_norma"}`."""
    resultado: list[dict] = []
    for tipo in TIPOS_NORMA_SUPORTADOS:
        registros = await buscar_lote_legislacao(tipo, maximum_records_por_tipo)
        for r in registros:
            if not r.get("url"):
                log.info("lexml_registro_sem_url_pulado", urn=r.get("urn"), tipo=tipo)
                continue
            resultado.append({**r, "tipo_norma": tipo})
    return resultado


async def baixar_texto_norma(url: str) -> str | None:
    """Baixa a página de publicação (tipicamente planalto.gov.br) e extrai o
    texto plano via BeautifulSoup (`beautifulsoup4`/`lxml` já são dependência
    do projeto — ver `app/integrations/tribunais/esaj.py`). Extração
    deliberadamente genérica (sem mirar seletor CSS de nenhum portal
    específico) pra tolerar tanto o portal legado (`ccivil_03`) quanto o mais
    novo (`www4.planalto.gov.br/legislacao`) sem saber qual foi resolvido.
    Fail-soft: qualquer falha de rede, parsing ou texto vazio devolve
    `None`, nunca lança."""
    async def _f():
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                log.warning("lexml_download_texto_http", status=resp.status_code, url=url)
                raise RuntimeError(f"download status {resp.status_code}")
            return resp.text

    html = await _breaker.run(_f, default=None)
    if html is None:
        return None
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        texto = soup.get_text(separator="\n")
        linhas = [l.strip() for l in texto.splitlines()]
        texto_limpo = "\n".join(l for l in linhas if l)
        return texto_limpo or None
    except Exception as exc:
        log.warning("lexml_extract_texto_falhou", url=url, error=str(exc))
        return None


async def buscar_norma_completa(registro: dict) -> dict | None:
    """Encadeia URL → texto pra 1 registro já descoberto. Devolve
    `{"fonte_documento_id", "titulo", "tipo_norma", "urn", "texto"}` ou
    `None` se o download/extração falhar — o chamador (task de sync) trata
    `None` como "pular este registro, seguir pro próximo" (fail-soft por
    documento, mesmo padrão de `stj_client.py`)."""
    url = registro.get("url")
    if not url:
        return None
    texto = await baixar_texto_norma(url)
    if not texto:
        return None
    return {
        "fonte_documento_id": registro["urn"],
        "titulo": registro.get("titulo"),
        "tipo_norma": registro.get("tipo_norma"),
        "urn": registro["urn"],
        "texto": texto,
    }
