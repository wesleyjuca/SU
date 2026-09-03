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


class DriveApiError(Exception):
    """Fase 258 — erro classificado de uma chamada à Drive API: carrega o
    status HTTP real e uma categoria estável (`token_expirado`,
    `permissao_negada`, `escopo_insuficiente`, `pasta_nao_encontrada`,
    `indisponivel`) pro chamador HTTP decidir o status/mensagem, sem
    reparsear a exceção crua em cada endpoint."""

    def __init__(self, categoria: str, status_code: int | None, mensagem: str):
        self.categoria = categoria
        self.status_code = status_code
        super().__init__(mensagem)


def _classificar_erro_drive(status_code: int, corpo: dict | None = None) -> DriveApiError:
    """`corpo` é o JSON de erro da Drive API quando disponível (formato
    `{"error": {"errors": [{"reason": "..."}]}}`) — usado só pra distinguir
    403 de permissão negada num item específico vs. 403 de escopo OAuth
    insuficiente (relevante pro google_workspace, que precisou ganhar
    `drive.metadata.readonly` pra poder listar pastas). Se o corpo estiver
    ausente ou não trouxer um `reason` reconhecível, cai no rótulo mais
    genérico — nunca afirma "escopo insuficiente" sem indício real."""
    if status_code == 401:
        return DriveApiError(
            "token_expirado", status_code, "Token expirado ou revogado — reconecte a integração."
        )
    if status_code == 403:
        motivo = ""
        try:
            motivo = ((corpo or {}).get("error", {}).get("errors", [{}])[0].get("reason") or "")
        except Exception:
            motivo = ""
        if "insufficientPermissions" in motivo or "insufficientScopes" in motivo:
            return DriveApiError(
                "escopo_insuficiente", status_code,
                "A conta conectada não concedeu permissão para listar pastas do Drive — "
                "reconecte a integração para conceder o acesso.",
            )
        return DriveApiError("permissao_negada", status_code, "Permissão negada pela conta Google conectada.")
    if status_code == 404:
        return DriveApiError(
            "pasta_nao_encontrada", status_code,
            "Pasta não encontrada — pode ter sido removida ou você perdeu acesso a ela.",
        )
    return DriveApiError("indisponivel", status_code, f"O Google Drive respondeu de forma inesperada (HTTP {status_code}).")


async def listar_pastas(access_token: str, parent_id: str | None = None) -> list[dict]:
    """Fase 258 — lista subpastas de `parent_id` (raiz do "Meu Drive" quando
    omitido) usando o token OAuth já conectado — substitui o fluxo de colar
    link/ID: nunca exige que a pasta seja pública ou compartilhada, só que a
    conta conectada a enxergue.

    Deliberadamente FORA do `_breaker` (diferente de `listar_arquivos`/
    `baixar_arquivo` abaixo): (a) uma listagem interativa disparada por
    clique do usuário não deve ficar presa atrás do circuito compartilhado
    com a sincronização em background — que pode estar "aberto" por uma
    falha de sync sem relação com a listagem; (b) `_breaker.run()` sempre
    engole a exceção da factory e devolve só `default`
    (`circuit_breaker.py::run`), o que perderia exatamente o status HTTP
    que `_classificar_erro_drive` precisa. Levanta `DriveApiError` — o
    endpoint HTTP decide o status/mensagem de resposta."""
    q = "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    q += f" and '{parent_id}' in parents" if parent_id else " and 'root' in parents"
    params = {
        "q": q,
        "fields": "files(id,name,parents)",
        "pageSize": 200,
        "orderBy": "name",
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.get(
                DRIVE_FILES_URL, params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError as exc:
            raise DriveApiError("indisponivel", None, f"Não foi possível contatar o Google Drive: {exc}") from exc
    if resp.status_code != 200:
        corpo = None
        try:
            corpo = resp.json()
        except Exception:
            corpo = None
        raise _classificar_erro_drive(resp.status_code, corpo)
    files = resp.json().get("files")
    return files if isinstance(files, list) else []

# Tipos de arquivo suportados pra extração de texto (doutrina = livros/
# artigos — DOCX/PDF/Google Doc nativo cobre o caso realista; o resto é
# logado e pulado).
_MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_MIME_PDF = "application/pdf"
# Doc nativo do Google Workspace (criado/escrito direto no Drive, não é
# upload de arquivo) — bem comum numa pasta de doutrina. Não é um blob
# binário: `alt=media` falha pra esse tipo (ver `baixar_conteudo` abaixo),
# precisa do endpoint `/export`.
_MIME_GDOC = "application/vnd.google-apps.document"

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
    """Baixa o conteúdo bruto de um arquivo binário (`alt=media`) — NÃO
    funciona pra Docs nativos do Google Workspace (usar `baixar_conteudo`)."""
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


async def _exportar_google_doc(access_token: str, file_id: str) -> bytes | None:
    """Exporta um Google Doc nativo como texto plano — arquivos nativos do
    Workspace (Docs/Sheets/Slides) não têm conteúdo binário próprio, então
    `alt=media` devolve erro; é preciso o endpoint `/export`."""
    async def _f():
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{DRIVE_FILES_URL}/{file_id}/export", params={"mimeType": "text/plain"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                log.warning("drive_export_http", status=resp.status_code, file_id=file_id)
                raise RuntimeError(f"drive export status {resp.status_code}")
            return resp.content

    return await _breaker.run(_f, default=None)


async def baixar_conteudo(access_token: str, file_id: str, mime_type: str | None) -> bytes | None:
    """Ponto único de download pro `google_drive_sync.py`: escolhe entre
    `alt=media` (arquivos binários normais) e `/export` (Docs nativos do
    Google) conforme o `mimeType`."""
    if mime_type == _MIME_GDOC:
        return await _exportar_google_doc(access_token, file_id)
    return await baixar_arquivo(access_token, file_id)


async def extrair_texto(mime_type: str | None, conteudo: bytes) -> str | None:
    """Extrai texto indexável do arquivo, conforme o `mimeType` que o Drive
    já devolve na listagem. `None` (não exceção) pra tipo não suportado ou
    extração vazia — o chamador loga e pula, fail-soft."""
    if not mime_type or not conteudo:
        return None
    if mime_type == _MIME_GDOC:
        # `conteudo` já chega como texto plano (exportado via `/export?
        # mimeType=text/plain` por `baixar_conteudo`) — só decodificar.
        texto = conteudo.decode("utf-8", errors="replace").strip()
        return texto or None
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
