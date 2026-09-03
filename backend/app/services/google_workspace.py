"""Google Workspace — helpers REST (httpx) do escritório (Fase 139).

Sem SDK do Google: chamadas REST diretas às APIs (Calendar, Drive, Gmail).
OAuth (URL de autorização, troca de code, refresh) é genérico e vive em
`app/services/integration_hub.py` (provider `"google_workspace"`, mesmo
mecanismo já usado por Stripe Connect/Mercado Pago/Google Drive doutrina) —
este módulo só guarda os helpers específicos de cada recurso do Google
(Calendar/Drive/Gmail), que recebem um `token: str` já pronto.

Antes da Fase 139 a conexão era por USUÁRIO (`GoogleIntegration`, cada
advogado conectava a própria conta) — agora é por TENANT (`TenantIntegration`,
1 conta única do escritório inteiro, decisão tomada com o usuário)."""
import base64
import json
from datetime import date, timedelta

import httpx

from app.services import integration_hub


class GoogleNotConnected(Exception):
    """Escritório sem conta Google do Workspace conectada (ou token inválido)."""


async def fetch_user_email(access_token: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code == 200:
                return resp.json().get("email")
    except Exception:
        pass
    return None


async def get_valid_token(db, tenant_id) -> str:
    """Access token válido da conta Google do escritório, renovando sozinho
    se preciso (`integration_hub.get_credentials` já trata refresh de forma
    genérica — mesmo mecanismo usado por `google_drive_doutrina`, Fase 138.2)."""
    creds = await integration_hub.get_credentials(db, tenant_id, "google_workspace")
    if not creds or not creds.get("access_token"):
        raise GoogleNotConnected("Conecte a conta Google do escritório em Integrações.")
    return creds["access_token"]


# ─── Helpers de recursos ─────────────────────────────────────────────────────
async def calendar_create_event(token: str, titulo: str, descricao: str, inicio_iso: str, fim_iso: str) -> dict:
    """Cria evento no calendário principal com lembretes padrão."""
    body = {
        "summary": titulo,
        "description": descricao,
        "start": {"dateTime": inicio_iso},
        "end": {"dateTime": fim_iso},
        "reminders": {"useDefault": False, "overrides": [
            {"method": "popup", "minutes": 24 * 60},
            {"method": "popup", "minutes": 60},
        ]},
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        resp.raise_for_status()
        d = resp.json()
        return {"id": d.get("id"), "link": d.get("htmlLink")}


async def calendar_create_allday_event(token: str, titulo: str, descricao: str, data: date) -> dict:
    """Cria evento de dia inteiro no calendário principal (ex.: prazo processual).

    Convenção de dia inteiro do Google Calendar: `end.date` é exclusivo, por
    isso é `data + 1 dia` — mesma convenção já usada no link manual do
    frontend (`googleCalendarUrl()` em agenda/page.tsx).
    """
    fim = data + timedelta(days=1)
    body = {
        "summary": titulo,
        "description": descricao,
        "start": {"date": data.isoformat()},
        "end": {"date": fim.isoformat()},
        "reminders": {"useDefault": False, "overrides": [
            {"method": "popup", "minutes": 24 * 60},
            {"method": "popup", "minutes": 60},
        ]},
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        resp.raise_for_status()
        d = resp.json()
        return {"id": d.get("id"), "link": d.get("htmlLink")}


async def _drive_upload(
    token: str, nome: str, content_bytes: bytes, source_mime: str, target_mime: str,
    parent_folder_id: str | None = None,
) -> dict:
    """Sobe um arquivo ao Drive do escritório (multipart upload). Quando
    `target_mime` é um formato nativo do Google (Doc/Sheet), a própria Drive
    API converte automaticamente durante o upload — evita chamar a Docs API
    ou a Sheets API diretamente, que exigiriam escopos OAuth próprios
    (`.../documents`, `.../spreadsheets`) não concedidos hoje. O escopo
    `drive.file` já autorizado (Fase 139) cobre esse upload+conversão.

    Fase 258 — `parent_folder_id` opcional: quando informado, o arquivo é
    criado dentro dessa pasta (`metadata["parents"]`) em vez de cair sempre
    na raiz ("Meu Drive"). `drive.file` já cobre criar em QUALQUER pasta
    pré-existente no momento da criação (mesmo uma não criada pela app) —
    só LISTAR pastas pré-existentes exigia o escopo novo
    `drive.metadata.readonly` (ver `integration_hub.py::OAUTH_PROVIDERS`).
    Sem pasta configurada, comportamento idêntico ao de antes desta fase."""
    metadata = {"name": nome, "mimeType": target_mime}
    if parent_folder_id:
        metadata["parents"] = [parent_folder_id]
    boundary = "afjcoreboundary"
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\nContent-Type: {source_mime}\r\n\r\n"
    ).encode() + content_bytes + f"\r\n--{boundary}--".encode()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,webViewLink",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            content=body,
        )
        resp.raise_for_status()
        d = resp.json()
        return {"id": d.get("id"), "link": d.get("webViewLink")}


async def drive_upload_pdf(token: str, nome: str, pdf_bytes: bytes, parent_folder_id: str | None = None) -> dict:
    """Sobe um PDF ao Drive do escritório (multipart upload)."""
    return await _drive_upload(
        token, f"{nome}.pdf", pdf_bytes, "application/pdf", "application/pdf", parent_folder_id,
    )


async def drive_upload_doc(token: str, nome: str, html_content: str, parent_folder_id: str | None = None) -> dict:
    """Sobe HTML ao Drive convertendo pro formato nativo Google Doc (Fase 182)
    — vira um documento colaborável de verdade, editável no Google Docs."""
    return await _drive_upload(
        token, nome, html_content.encode("utf-8"), "text/html", "application/vnd.google-apps.document",
        parent_folder_id,
    )


async def drive_upload_sheet(token: str, nome: str, csv_bytes: bytes, parent_folder_id: str | None = None) -> dict:
    """Sobe CSV ao Drive convertendo pro formato nativo Google Sheets (Fase 182)
    — vira uma planilha colaborável de verdade, editável no Google Sheets."""
    return await _drive_upload(
        token, nome, csv_bytes, "text/csv", "application/vnd.google-apps.spreadsheet", parent_folder_id,
    )


async def get_configured_folder_id(db, tenant_id) -> str | None:
    """Fase 258 — lê o folder_id de salvamento configurado para
    google_workspace, ou None se não configurado (upload cai na raiz,
    comportamento atual preservado)."""
    from app.services import integration_hub

    integ = await integration_hub.get_integration(db, tenant_id, "google_workspace")
    return (integ.extra_data or {}).get("folder_id") if integ else None


def classificar_erro_upload_drive(exc: httpx.HTTPStatusError) -> tuple[int, str]:
    """Fase 258 — traduz o `httpx.HTTPStatusError` que `_drive_upload`
    levanta (via `resp.raise_for_status()`) numa mensagem específica
    (token expirado/revogado, permissão negada, pasta removida), em vez do
    genérico "Erro ao salvar no Google Drive." que os 3 call sites usavam
    antes desta fase. Reusa a mesma classificação já usada na listagem de
    pastas — sem duplicar a lógica em cada endpoint. Devolve
    `(status_http, mensagem)` — sem depender de FastAPI aqui (este módulo
    é REST puro), o chamador HTTP monta o `HTTPException`."""
    from app.integrations.google_drive.client import _classificar_erro_drive

    corpo = None
    try:
        corpo = exc.response.json()
    except Exception:
        corpo = None
    erro = _classificar_erro_drive(exc.response.status_code, corpo)
    status = {
        "token_expirado": 401,
        "permissao_negada": 403,
        "escopo_insuficiente": 403,
        "pasta_nao_encontrada": 404,
    }.get(erro.categoria, 502)
    return status, str(erro)


async def gmail_send(token: str, to: str, subject: str, html_body: str) -> bool:
    """Envia e-mail pela conta Google conectada (Gmail API)."""
    mime = (
        f"To: {to}\r\nSubject: {subject}\r\n"
        "Content-Type: text/html; charset=UTF-8\r\n\r\n"
        f"{html_body}"
    )
    raw = base64.urlsafe_b64encode(mime.encode()).decode()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {token}"},
            json={"raw": raw},
        )
        resp.raise_for_status()
        return True
