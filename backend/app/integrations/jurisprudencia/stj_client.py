"""Cliente do portal de dados abertos do STJ (Fase 138.1) — ingestão
automática de acórdãos/decisões, fail-soft.

O STJ publica jurisprudência em texto integral via um portal de dados
abertos baseado em CKAN (`dadosabertos.web.stj.jus.br`), dataset "Íntegras
de Decisões Terminativas e Acórdãos do Diário da Justiça" — carga inicial +
atualização diária incremental por arquivo (padrão de nome `YYYYMM`),
licença CC-BY. A API de ações do CKAN (`/api/3/action/package_show`) é um
padrão público, estável e bem documentado (usado por dezenas de portais de
dados abertos governamentais) — é isso que este cliente implementa com
confiança.

O que NÃO é verificável neste ambiente (egress bloqueado pro domínio no
sandbox, mesma limitação de sempre nesta sessão — OpenRouter/PDPJ/Escavador/
Judit/LexML): o `dataset_id` exato do STJ nesse portal, e o formato interno
exato de cada decisão dentro do arquivo ZIP publicado (nomes de campo JSON,
se há um `.txt` por decisão ou tudo num JSON só). `parsear_pacote()` tenta
várias formas plausíveis e degrada pra lista vazia (nunca lança) se nada
bater — o teste de ponta-a-ponta contra o portal real fica por conta de quem
fizer o deploy, na primeira execução do sync."""
from __future__ import annotations

import json
import zipfile
import hashlib
import io

import httpx
import structlog

from app.integrations.fontes.circuit_breaker import CircuitBreaker

log = structlog.get_logger()

STJ_CKAN_BASE_URL = "https://dadosabertos.web.stj.jus.br"
# Não confirmado contra o portal real (ver docstring do módulo) — melhor
# palpite grounded pela pesquisa; ajustar assim que confirmado em produção.
STJ_DATASET_ID = "integras-de-decisoes-terminativas-e-acordaos-do-diario-da-justica"

_TIMEOUT = 30.0
_breaker = CircuitBreaker(name="stj_dados_abertos")

# Aliases plausíveis de nome de campo — o dataset real pode usar qualquer um
# destes (ou outro não previsto, daí o fallback pra None/campo ausente).
_ALIASES = {
    "numero_processo": ("numero_processo", "numeroProcesso", "processo", "numero"),
    "relator": ("relator", "nome_relator", "ministro_relator", "relatorNome"),
    "data": ("data", "data_julgamento", "dataJulgamento", "data_publicacao"),
    "orgao_julgador": ("orgao_julgador", "orgaoJulgador", "orgao", "turma"),
    "ementa": ("ementa", "ementaTexto"),
    "texto": ("texto", "inteiro_teor", "inteiroTeor", "conteudo"),
}


def _primeiro_campo(d: dict, chave: str) -> str | None:
    for alias in _ALIASES[chave]:
        val = d.get(alias)
        if val:
            return str(val)
    return None


async def listar_recursos() -> list[dict] | None:
    """Lista os recursos (arquivos) do dataset via CKAN `package_show`.
    Devolve `None` se não foi possível consultar (rede, circuito aberto,
    resposta inesperada) — distinto de "lista vazia" (dataset sem recursos)."""
    async def _f():
        url = f"{STJ_CKAN_BASE_URL}/api/3/action/package_show"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params={"id": STJ_DATASET_ID})
            if resp.status_code != 200:
                log.warning("stj_http", status=resp.status_code)
                raise RuntimeError(f"stj status {resp.status_code}")
            return resp.json()

    data = await _breaker.run(_f, default=None)
    if not data or not isinstance(data, dict) or not data.get("success"):
        return None
    resources = (data.get("result") or {}).get("resources")
    if not isinstance(resources, list):
        return None
    return resources


def resource_mais_recente(resources: list[dict]) -> dict | None:
    """Escolhe o recurso mais recente por `last_modified`/`created`
    (fallback pro nome, já que o padrão observado é `YYYYMM`, ordenável
    como string)."""
    if not resources:
        return None

    def _chave(r: dict):
        return (r.get("last_modified") or r.get("created") or "", r.get("name") or "")

    return max(resources, key=_chave)


async def baixar_recurso(url: str) -> bytes | None:
    """Baixa o conteúdo bruto de um recurso (arquivo ZIP, tipicamente)."""
    async def _f():
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                log.warning("stj_download_http", status=resp.status_code, url=url)
                raise RuntimeError(f"download status {resp.status_code}")
            return resp.content

    return await _breaker.run(_f, default=None)


def parsear_pacote(conteudo: bytes) -> list[dict]:
    """Extrai decisões de um pacote ZIP baixado do portal. Tolerante ao
    formato interno exato (ver docstring do módulo) — tenta interpretar
    entradas `.json` como registros de decisão, ignora o resto; nunca lança,
    degrada pra lista vazia se nada for reconhecível.

    Cada item devolvido: {"fonte_documento_id", "numero_processo", "relator",
    "data", "orgao_julgador", "texto"} — `texto` é o conteúdo indexável
    (ementa + inteiro teor, o que estiver disponível)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile:
        log.warning("stj_pacote_nao_e_zip")
        return []

    registros = []
    for nome in zf.namelist():
        if not nome.lower().endswith(".json"):
            continue
        try:
            raw = zf.read(nome)
            item = json.loads(raw)
        except Exception as exc:
            log.warning("stj_entrada_ilegivel", arquivo=nome, error=str(exc))
            continue
        if not isinstance(item, dict):
            continue

        texto = _primeiro_campo(item, "texto") or _primeiro_campo(item, "ementa") or ""
        if not texto.strip():
            # Sem texto indexável — decisão sem conteúdo útil pro RAG, pula.
            continue

        fonte_documento_id = (
            _primeiro_campo(item, "numero_processo")
            or nome
            or hashlib.sha256(raw).hexdigest()[:32]
        )
        registros.append({
            "fonte_documento_id": fonte_documento_id,
            "numero_processo": _primeiro_campo(item, "numero_processo"),
            "relator": _primeiro_campo(item, "relator"),
            "data": _primeiro_campo(item, "data"),
            "orgao_julgador": _primeiro_campo(item, "orgao_julgador"),
            "texto": texto,
        })

    if not registros:
        log.warning("stj_pacote_sem_registros_reconheciveis", entradas=len(zf.namelist()))
    return registros


async def buscar_lote_recente() -> list[dict]:
    """Ponto de entrada usado pela task de sincronização: lista recursos,
    baixa o mais recente, parseia. Fail-soft em cada etapa — devolve lista
    vazia (não erro) se qualquer passo falhar, pra sync_stj_diario() poder
    registrar "0 processados" em vez de quebrar."""
    recursos = await listar_recursos()
    if not recursos:
        return []
    recurso = resource_mais_recente(recursos)
    if not recurso or not recurso.get("url"):
        return []
    conteudo = await baixar_recurso(recurso["url"])
    if conteudo is None:
        return []
    return parsear_pacote(conteudo)
