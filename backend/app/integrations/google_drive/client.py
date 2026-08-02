"""Cliente REST da API do Google Drive v3 (Fase 138.2) — listagem/download de
arquivos de uma pasta configurada pelo ADMIN, fail-soft. Ao contrário do
cliente do STJ (Fase 138.1), o shape da API do Drive v3 é público, estável
e bem documentado — a única coisa não testável neste ambiente é o fluxo
OAuth de ponta-a-ponta em si (precisa de um redirect real do Google)."""
from __future__ import annotations

import re

import httpx
import structlog

from app.integrations.fontes.circuit_breaker import CircuitBreaker

log = structlog.get_logger()

DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
_TIMEOUT = 30.0
_breaker = CircuitBreaker(name="google_drive")

# Tipos de arquivo suportados pra extração de texto (doutrina = livros/
# artigos — DOCX/PDF cobre o caso realista; o resto é logado e pulado).
_MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_MIME_PDF = "application/pdf"

# Aceita URL completa (com ou sem /u/0/, com ou sem query string) ou ID cru.
_PADRAO_URL_PASTA = re.compile(r"drive\.google\.com/drive/(?:u/\d+/)?folders/([a-zA-Z0-9_-]+)")
_PADRAO_ID_CRU = re.compile(r"^[a-zA-Z0-9_-]{10,}$")


def extrair_folder_id(texto: str) -> str | None:
    """Extrai o ID da pasta a partir de uma URL do Drive ou de um ID colado
    direto. `None` se o formato não for reconhecível — o chamador decide
    como reportar isso ao usuário (nunca lança daqui)."""
    if not texto:
        return None
    texto = texto.strip()
    m = _PADRAO_URL_PASTA.search(texto)
    if m:
        return m.group(1)
    if _PADRAO_ID_CRU.match(texto):
        return texto
    return None


async def listar_arquivos(access_token: str, folder_id: str) -> list[dict] | None:
    """Lista arquivos (não-pastas, não-lixeira) dentro da pasta configurada.
    Devolve `None` se a chamada falhar (rede, token inválido, circuito
    aberto) — distinto de lista vazia (pasta existente mas sem arquivos)."""
    async def _f():
        params = {
            "q": f"'{folder_id}' in parents and trashed=false and mimeType != 'application/vnd.google-apps.folder'",
            "fields": "files(id,name,mimeType,modifiedTime)",
            "pageSize": 100,
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                DRIVE_FILES_URL, params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                log.warning("drive_list_http", status=resp.status_code)
                raise RuntimeError(f"drive list status {resp.status_code}")
            return resp.json()

    data = await _breaker.run(_f, default=None)
    if not data or not isinstance(data, dict):
        return None
    files = data.get("files")
    return files if isinstance(files, list) else None


async def baixar_arquivo(access_token: str, file_id: str) -> bytes | None:
    """Baixa o conteúdo bruto de um arquivo (`alt=media`)."""
    async def _f():
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{DRIVE_FILES_URL}/{file_id}", params={"alt": "media"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                log.warning("drive_download_http", status=resp.status_code, file_id=file_id)
                raise RuntimeError(f"drive download status {resp.status_code}")
            return resp.content

    return await _breaker.run(_f, default=None)


async def extrair_texto(mime_type: str | None, conteudo: bytes) -> str | None:
    """Extrai texto indexável do arquivo, conforme o `mimeType` que o Drive
    já devolve na listagem. `None` (não exceção) pra tipo não suportado ou
    extração vazia — o chamador loga e pula, fail-soft."""
    if not mime_type or not conteudo:
        return None
    if mime_type == _MIME_DOCX:
        try:
            from app.utils.docx_text import extract_docx_text
            texto = extract_docx_text(conteudo)
            return texto or None
        except Exception as exc:
            log.warning("drive_extract_docx_falhou", error=str(exc))
            return None
    if mime_type == _MIME_PDF:
        try:
            from app.agents.ocr.ocr_agent import OCRAgent
            from app.agents.brain.context import AgentContext
            from app.agents.base.result import AgentStatus
            import base64

            ctx = AgentContext(
                task_type="ocr_document",
                task_input={
                    "file_bytes_b64": base64.b64encode(conteudo).decode(),
                    "content_type": _MIME_PDF,
                },
            )
            result = await OCRAgent(db=None).execute(ctx)
            if result.status != AgentStatus.SUCCESS:
                return None
            texto = (result.output or {}).get("texto_extraido") or ""
            if texto == OCRAgent.UNAVAILABLE or not texto.strip():
                return None
            return texto
        except Exception as exc:
            log.warning("drive_extract_pdf_falhou", error=str(exc))
            return None
    log.info("drive_tipo_nao_suportado", mime_type=mime_type)
    return None
