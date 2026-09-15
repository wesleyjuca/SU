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

import ipaddress
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx
import structlog
from defusedxml import DefusedXmlException
from defusedxml import ElementTree as DefusedET

from app.integrations.fontes.circuit_breaker import CircuitBreaker

log = structlog.get_logger()

LEXML_SRU_URL = "https://www.lexml.gov.br/busca/SRU"
_TIMEOUT = 15.0
_breaker = CircuitBreaker(name="lexml")

# Identificação em chamada a API pública de dado aberto — boa prática de
# cidadania (permite ao operador do portal nos contatar em vez de bloquear no
# escuro). Antes, o cliente caía no default do httpx ("python-httpx/x.x.x").
#
# RISCO CONHECIDO, registrado de propósito: um User-Agent autoidentificado foi
# a causa-raiz confirmada do HTTP 403 do WAF do Comunica/DJEN (ver
# `integrations/dje/comunica.py`). O LexML é acervo de dados abertos `.gov.br`,
# não portal de consulta processual protegido, e nunca apresentou 403 — mas se
# um dia apresentar, ESTE É O PRIMEIRO SUSPEITO: basta remover o header.
_USER_AGENT = "AFJ-Core/1.0 (+https://afjadvogados.com.br; sistema juridico)"
_HEADERS = {"User-Agent": _USER_AGENT}

# Teto de resposta antes do parse. O `defusedxml` já barra expansão de
# entidade (billion laughs), mas não impede um corpo gigante de consumir
# memória só para o parser descobrir que é grande demais.
_MAX_RESPOSTA_BYTES = 8 * 1024 * 1024  # 8 MB

# Allowlist de domínio para `baixar_texto_norma`. Sem isto, a função faz GET
# numa URL que veio DA RESPOSTA EXTERNA — SSRF clássico: o portal (ou quem o
# comprometer) escolheria o alvo, incluindo `169.254.169.254` (metadata de
# nuvem) ou um serviço interno. Sufixos amplos o bastante para o universo real
# de provedores de dados do LexML (Planalto, Senado, Câmara, tribunais), e
# estreitos o bastante para excluir qualquer host arbitrário.
_SUFIXOS_PERMITIDOS = (".gov.br", ".leg.br", ".jus.br", ".mp.br", ".def.br")
_MAX_REDIRECTS = 5


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _fromstring_seguro(xml_text: str) -> ET.Element | None:
    """Parse de XML vindo de fonte externa. `None` (nunca exceção) em qualquer
    problema — o chamador já trata `None` como "não verificável".

    Medido neste projeto: `xml.etree.ElementTree` **recusa** entidade externa
    (XXE não se aplica), mas **aceita** expansão de entidade interna, que é o
    vetor de DoS de memória. `defusedxml` fecha esse.
    """
    if len(xml_text.encode("utf-8", errors="ignore")) > _MAX_RESPOSTA_BYTES:
        log.warning("lexml_xml_grande_demais", tamanho=len(xml_text))
        return None
    try:
        return DefusedET.fromstring(xml_text)
    except (ET.ParseError, DefusedXmlException, ValueError) as exc:
        log.warning("lexml_xml_invalido", error=str(exc)[:200])
        return None


def url_permitida(url: str) -> bool:
    """`True` se a URL pode ser buscada por `baixar_texto_norma`.

    Rejeita: esquema fora de http/https, host ausente, IP literal (fecha o
    acesso a metadata de nuvem e à rede interna) e qualquer host fora dos
    sufixos oficiais brasileiros.
    """
    try:
        partes = urlparse(url)
    except ValueError:
        return False
    if partes.scheme not in ("http", "https"):
        return False
    host = (partes.hostname or "").lower()
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
        return False  # IP literal nunca é um portal legislativo legítimo
    except ValueError:
        pass
    return any(host == s.lstrip(".") or host.endswith(s) for s in _SUFIXOS_PERMITIDOS)


def _parsear_resposta(xml_text: str) -> dict | None:
    root = _fromstring_seguro(xml_text)
    if root is None:
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
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
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


def _numero_de_registros(root: ET.Element) -> int | None:
    """`numberOfRecords` do envelope SRU, ou `None` se o campo não existir.

    É o **discriminador** entre "o portal respondeu e não achou nada" e "o
    portal respondeu num formato que este parser não entende" — dois desfechos
    que antes viravam a mesma lista vazia. Se este campo aparece, nosso
    entendimento do envelope SRU está correto; se não aparece, está errado, e
    é isso que o diagnóstico precisa dizer.
    """
    for el in root.iter():
        if _local(el.tag) == "numberOfRecords" and el.text:
            bruto = el.text.strip()
            if bruto.isdigit():
                return int(bruto)
    return None


def _registros_de(root: ET.Element) -> list[dict]:
    """Extrai todos os <record> de uma árvore SRU já parseada."""
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


def _parsear_registros(xml_text: str) -> list[dict]:
    """Extrai todos os <record> de uma resposta SRU multi-registro (ao
    contrário de `_parsear_resposta`, que só olha o 1º). Um <record>
    malformado ou sem `urn` é pulado, não derruba os demais. Nunca lança —
    XML não parseável devolve `[]`."""
    root = _fromstring_seguro(xml_text)
    if root is None:
        return []
    return _registros_de(root)


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
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
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
    `None`, nunca lança.

    A URL vem da resposta do LexML, não de nós — por isso passa por
    `url_permitida()` antes, e **cada salto de redirect é revalidado**. Um
    `follow_redirects=True` simples deixaria o portal redirecionar para
    qualquer lugar, anulando a allowlist."""
    if not url_permitida(url):
        log.warning("lexml_url_bloqueada", url=url[:200])
        return None

    async def _f():
        # follow_redirects desligado de propósito: seguimos à mão para poder
        # validar o destino de cada salto contra a allowlist.
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=False) as client:
            alvo = url
            for _ in range(_MAX_REDIRECTS):
                resp = await client.get(alvo)
                if resp.is_redirect:
                    destino = str(resp.next_request.url) if resp.next_request else ""
                    if not url_permitida(destino):
                        log.warning("lexml_redirect_bloqueado", de=alvo[:120], para=destino[:120])
                        raise RuntimeError("redirect para host fora da allowlist")
                    alvo = destino
                    continue
                if resp.status_code != 200:
                    log.warning("lexml_download_texto_http", status=resp.status_code, url=alvo[:200])
                    raise RuntimeError(f"download status {resp.status_code}")
                return resp.text
            raise RuntimeError("excesso de redirects")

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


# ─── Integração LexML — busca sob demanda (disparada pelo advogado) ───────────

def montar_query_cql(texto: str, tipo_norma: str | None = None) -> str:
    """Monta a CQL de uma busca sob demanda usando SÓ o que está provado.

    Duas formas são provadas em produção neste projeto, por estarem em uso:
    texto livre como `query` inteira (`buscar_lei`, via `citacao_check`) e
    `localidade=federal and tipoDocumento=X` (`buscar_lote_legislacao`, na
    sincronização diária). O operador `and` entre elas é CQL padrão e cada
    metade é provada isolada — a COMBINAÇÃO não foi verificada contra o
    portal real (egress bloqueado no ambiente de desenvolvimento).

    Os índices `ano` e `autoridade` **não** entram aqui: nunca foram vistos
    respondendo, e um índice inexistente pode derrubar a busca inteira. Esses
    filtros são aplicados no acervo local, depois (ver
    `services/lexml_acervo.py`). Se um dia uma sonda real confirmar os
    índices, movê-los para a CQL é otimização, não correção.
    """
    termo = " ".join((texto or "").split()).strip()

    # Fase pós-266.2 — a "forma provada" era mais estreita do que eu registrei.
    # O que `citacao_check` manda há muito tempo, e que sabidamente responde, é
    # uma REFERÊNCIA NUMÉRICA normalizada ("8078/1990") — nunca uma frase em
    # linguagem natural. Quando o texto digitado contém uma referência assim,
    # é ela que vai; caso contrário segue a frase como antes, e agora o
    # diagnóstico dirá se o índice padrão do SRU a atende.
    if termo:
        from app.services.citacao_check import extrair_referencias_lei

        referencias = extrair_referencias_lei(termo)
        if referencias:
            termo = referencias[0]

    if tipo_norma:
        tipo = tipo_norma.strip()
        filtro = f"localidade=federal and tipoDocumento={tipo}"
        return f"{termo} and {filtro}" if termo else filtro
    return termo


async def buscar_normas_com_diagnostico(
    texto: str, tipo_norma: str | None = None, limite: int = 20
) -> tuple[list[dict], dict]:
    """Busca normas no SRU e devolve `(registros, diagnostico)`.

    Existe porque a lista vazia sozinha é ambígua: ela era o retorno de CINCO
    desfechos distintos — circuito aberto (nem tentou), HTTP não-200, erro de
    rede, XML num schema que este parser não entende, e o portal respondendo
    200 com zero registros, que é resposta legítima e não falha. A tela
    afirmava "o portal não respondeu" nos cinco, o que é falso em três deles.
    É a armadilha "fail-soft engole o sinal" já catalogada no CLAUDE.md.

    `diagnostico["desfecho"]` é um de: `ok`, `vazio`, `circuito_aberto`,
    `http`, `rede`, `xml_ilegivel`, `schema_inesperado`, `sem_criterio`.
    Nunca lança — quem chama está num caminho síncrono de usuário.
    """
    query = montar_query_cql(texto, tipo_norma)
    diagnostico: dict = {
        "desfecho": "sem_criterio", "query": query,
        "status_code": None, "body_snippet": None, "number_of_records": None,
    }
    if not query:
        return [], diagnostico
    limite = max(1, min(int(limite or 20), 100))

    # O breaker devolve o mesmo `default` para "circuito aberto" e para
    # "a chamada falhou" — esta flag é o que distingue os dois sem uma leitura
    # extra do Redis e sem corrida entre checar e chamar.
    tentou = False

    async def _f():
        nonlocal tentou
        tentou = True
        params = {
            "operation": "searchRetrieve",
            "version": "1.1",
            "query": query,
            "maximumRecords": str(limite),
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
            try:
                resp = await client.get(LEXML_SRU_URL, params=params)
            except Exception as exc:
                diagnostico["desfecho"] = "rede"
                diagnostico["body_snippet"] = f"{type(exc).__name__}: {exc}"[:500]
                raise
            if resp.status_code != 200:
                # Capturado ANTES de levantar: dentro do breaker o status
                # sumiria junto com a exceção (mesmo padrão de `dje/comunica.py`).
                diagnostico["desfecho"] = "http"
                diagnostico["status_code"] = resp.status_code
                diagnostico["body_snippet"] = (resp.text or "")[:500]
                log.warning("lexml_busca_http", status=resp.status_code)
                raise RuntimeError(f"lexml status {resp.status_code}")
            diagnostico["status_code"] = 200
            return resp.text

    xml_text = await _breaker.run(_f, default=None)
    if xml_text is None:
        if not tentou:
            diagnostico["desfecho"] = "circuito_aberto"
        elif diagnostico["desfecho"] not in ("http", "rede"):
            diagnostico["desfecho"] = "rede"  # exceção fora dos ramos instrumentados
        log.warning("lexml_busca_sem_resposta", desfecho=diagnostico["desfecho"])
        return [], diagnostico

    root = _fromstring_seguro(xml_text)
    if root is None:
        diagnostico["desfecho"] = "xml_ilegivel"
        diagnostico["body_snippet"] = xml_text[:500]
        return [], diagnostico

    diagnostico["number_of_records"] = _numero_de_registros(root)
    registros = _registros_de(root)
    if registros:
        diagnostico["desfecho"] = "ok"
    elif diagnostico["number_of_records"] == 0:
        diagnostico["desfecho"] = "vazio"  # respondeu e não achou — não é falha
    else:
        # 200 com XML válido, mas sem `numberOfRecords` reconhecível ou com
        # registros que não conseguimos ler: o schema não é o que o parser
        # assume. É o ponto que o plano marcava como NÃO VERIFICADO — o
        # snippet é o insumo para corrigir o parser na próxima fase.
        diagnostico["desfecho"] = "schema_inesperado"
        diagnostico["body_snippet"] = xml_text[:500]
    return registros, diagnostico


async def buscar_normas(texto: str, tipo_norma: str | None = None, limite: int = 20) -> list[dict]:
    """Wrapper fino sobre `buscar_normas_com_diagnostico` para quem só quer a
    lista (mesmo idioma de `embed_text` sobre `embed_text_with_meta`)."""
    registros, _ = await buscar_normas_com_diagnostico(texto, tipo_norma, limite)
    return registros
