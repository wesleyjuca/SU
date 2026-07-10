"""Google Workspace — tokens OAuth (com refresh) e helpers REST (httpx).

Sem SDK do Google: chamadas REST diretas às APIs (Calendar, Drive, Gmail).
Tokens ficam cifrados em GoogleIntegration; o access_token é renovado
automaticamente via refresh_token quando expirado.
"""
import base64
import json
from datetime import datetime, timedelta, timezone

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.crypto import encrypt, decrypt
from app.models.integrations import GoogleIntegration

log = structlog.get_logger()

OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.email",
]


class GoogleNotConnected(Exception):
    """Usuário sem conta Google conectada (ou tokens inválidos)."""


def is_configured() -> bool:
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET and settings.GOOGLE_REDIRECT_URI)


def build_auth_url(state: str) -> str:
    from urllib.parse import urlencode
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",   # garante refresh_token na primeira conexão
        "state": state,
    }
    return f"{OAUTH_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    """Troca o authorization code por tokens."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(OAUTH_TOKEN_URL, data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        resp.raise_for_status()
        return resp.json()


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


async def get_valid_token(db: AsyncSession, user_id) -> str:
    """Access token válido do usuário, renovando via refresh_token se preciso."""
    integ = (await db.execute(
        select(GoogleIntegration).where(GoogleIntegration.user_id == user_id)
    )).scalar_one_or_none()
    if not integ or not integ.refresh_token_enc:
        raise GoogleNotConnected("Conecte sua conta Google em Integrações.")

    now = datetime.now(timezone.utc)
    expiry = integ.token_expiry
    if expiry is not None and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    access = decrypt(integ.access_token_enc)
    if access and expiry and expiry > now + timedelta(seconds=60):
        return access

    # Renova
    refresh = decrypt(integ.refresh_token_enc)
    if not refresh:
        raise GoogleNotConnected("Reconecte sua conta Google (token inválido).")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(OAUTH_TOKEN_URL, data={
            "refresh_token": refresh,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "grant_type": "refresh_token",
        })
        if resp.status_code != 200:
            log.warning("google_refresh_failed", status=resp.status_code)
            raise GoogleNotConnected("Sessão Google expirada — reconecte em Integrações.")
        data = resp.json()

    integ.access_token_enc = encrypt(data["access_token"])
    integ.token_expiry = now + timedelta(seconds=int(data.get("expires_in", 3600)))
    await db.flush()
    return data["access_token"]


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


async def drive_upload_pdf(token: str, nome: str, pdf_bytes: bytes) -> dict:
    """Sobe um PDF ao Drive do usuário (multipart upload)."""
    metadata = {"name": f"{nome}.pdf", "mimeType": "application/pdf"}
    boundary = "afjcoreboundary"
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\nContent-Type: application/pdf\r\n\r\n"
    ).encode() + pdf_bytes + f"\r\n--{boundary}--".encode()
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
