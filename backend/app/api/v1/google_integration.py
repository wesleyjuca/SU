"""Google Workspace — OAuth por usuário + ações (Agenda, Drive)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
import uuid

from app.config import settings
from app.db.base import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.integrations import GoogleIntegration
from app.core.crypto import encrypt

router = APIRouter(prefix="/integrations/google", tags=["google"])

_NOT_CONFIGURED = (
    "Integração Google não configurada no servidor. O administrador precisa criar "
    "credenciais OAuth no Google Cloud Console e definir GOOGLE_CLIENT_ID, "
    "GOOGLE_CLIENT_SECRET e GOOGLE_REDIRECT_URI no Railway (instruções em Integrações)."
)

_MODULE_DISABLED = (
    "A integração Google Workspace está desabilitada para este escritório. "
    "O administrador pode habilitá-la em Integrações."
)


async def _google_enabled(db: AsyncSession, tenant_id) -> bool:
    """O módulo Google é opcional por escritório (opt-in do ADMIN do tenant)."""
    from app.models.tenant import TenantConfig
    if not tenant_id:
        return False
    cfg = (await db.execute(
        select(TenantConfig).where(TenantConfig.tenant_id == tenant_id)
    )).scalar_one_or_none()
    return bool(cfg and (cfg.modules_enabled or {}).get("google_workspace", False))


def _sign_state(user_id: str) -> str:
    from jose import jwt
    return jwt.encode(
        {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(minutes=10), "purpose": "google_oauth"},
        settings.SECRET_KEY, algorithm="HS256",
    )


def _verify_state(state: str) -> str:
    from jose import jwt, JWTError
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=["HS256"])
        if payload.get("purpose") != "google_oauth":
            raise JWTError("purpose")
        return payload["sub"]
    except JWTError:
        raise HTTPException(status_code=400, detail="State OAuth inválido ou expirado. Tente conectar novamente.")


@router.get("/status")
async def google_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.google_workspace import is_configured
    enabled = await _google_enabled(db, current_user.tenant_id)
    integ = (await db.execute(
        select(GoogleIntegration).where(GoogleIntegration.user_id == current_user.id)
    )).scalar_one_or_none()
    return {
        "enabled": enabled,   # opt-in do escritório (decisão do ADMIN do tenant)
        "configured": is_configured(),
        "connected": bool(enabled and integ and integ.refresh_token_enc),
        "google_email": integ.google_email if integ else None,
    }


@router.post("/connect")
async def google_connect(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Gera a URL de autorização OAuth para o usuário conectar sua conta."""
    from app.services.google_workspace import is_configured, build_auth_url
    if not await _google_enabled(db, current_user.tenant_id):
        raise HTTPException(status_code=422, detail=_MODULE_DISABLED)
    if not is_configured():
        raise HTTPException(status_code=422, detail=_NOT_CONFIGURED)
    return {"auth_url": build_auth_url(_sign_state(str(current_user.id)))}


@router.get("/callback")
async def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Retorno do Google: troca o code por tokens e salva cifrado."""
    from app.services.google_workspace import exchange_code, fetch_user_email

    user_id = uuid.UUID(_verify_state(state))
    try:
        data = await exchange_code(code)
    except Exception:
        return RedirectResponse(url="/integracoes?google=erro")

    now = datetime.now(timezone.utc)
    integ = (await db.execute(
        select(GoogleIntegration).where(GoogleIntegration.user_id == user_id)
    )).scalar_one_or_none()
    if not integ:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        integ = GoogleIntegration(user_id=user_id, tenant_id=user.tenant_id if user else None)
        db.add(integ)

    integ.access_token_enc = encrypt(data["access_token"])
    if data.get("refresh_token"):
        integ.refresh_token_enc = encrypt(data["refresh_token"])
    integ.token_expiry = now + timedelta(seconds=int(data.get("expires_in", 3600)))
    integ.scopes = data.get("scope")
    integ.google_email = await fetch_user_email(data["access_token"])
    await db.flush()
    return RedirectResponse(url="/integracoes?google=ok")


@router.delete("/disconnect")
async def google_disconnect(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    integ = (await db.execute(
        select(GoogleIntegration).where(GoogleIntegration.user_id == current_user.id)
    )).scalar_one_or_none()
    if integ:
        # Revogação best-effort no Google
        try:
            import httpx
            from app.core.crypto import decrypt
            token = decrypt(integ.refresh_token_enc) or decrypt(integ.access_token_enc)
            if token:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post("https://oauth2.googleapis.com/revoke", params={"token": token})
        except Exception:
            pass
        await db.delete(integ)
        await db.flush()
    return {"message": "Conta Google desconectada."}


# ─── Ações integradas ─────────────────────────────────────────────────────────
class CalendarEventCreate(BaseModel):
    titulo: str
    descricao: str | None = None
    data: str          # YYYY-MM-DD
    hora: str = "09:00"


@router.post("/calendar-event", status_code=201)
async def create_calendar_event(
    body: CalendarEventCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cria o prazo/compromisso direto no Google Agenda do usuário conectado."""
    from app.services.google_workspace import get_valid_token, calendar_create_event, GoogleNotConnected
    if not await _google_enabled(db, current_user.tenant_id):
        raise HTTPException(status_code=422, detail=_MODULE_DISABLED)
    try:
        token = await get_valid_token(db, current_user.id)
        inicio = f"{body.data}T{body.hora}:00-05:00"  # fuso do Acre (UTC-5)
        fim_h = f"{int(body.hora[:2]) + 1:02d}{body.hora[2:]}"
        fim = f"{body.data}T{fim_h}:00-05:00"
        result = await calendar_create_event(token, body.titulo, body.descricao or "", inicio, fim)
        return {"message": "Evento criado no Google Agenda.", **result}
    except GoogleNotConnected as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=502, detail="Erro ao criar o evento no Google Agenda.")


@router.post("/drive-save/{doc_id}", status_code=201)
async def save_document_to_drive(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Gera o PDF timbrado do documento e salva no Google Drive do usuário."""
    from app.services.google_workspace import get_valid_token, drive_upload_pdf, GoogleNotConnected
    from app.models.document import Document
    from app.models.tenant import TenantConfig
    from app.utils.pdf_builder import build_petition_pdf
    from app.core.exceptions import NotFoundError

    if not await _google_enabled(db, current_user.tenant_id):
        raise HTTPException(status_code=422, detail=_MODULE_DISABLED)

    doc = (await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(doc_id),
            Document.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Documento", doc_id)

    letterhead = None
    try:
        cfg = (await db.execute(
            select(TenantConfig).where(TenantConfig.tenant_id == current_user.tenant_id)
        )).scalar_one_or_none()
        if cfg:
            letterhead = dict((cfg.document_templates or {}).get("letterhead", {}))
            if cfg.logo_url:
                letterhead["logo_data_url"] = cfg.logo_url
    except Exception:
        letterhead = None

    pdf = build_petition_pdf(
        title=doc.titulo,
        content_html=doc.conteudo_html or doc.conteudo_texto or "",
        metadata={"status": doc.status},
        letterhead=letterhead,
    )
    try:
        token = await get_valid_token(db, current_user.id)
        result = await drive_upload_pdf(token, doc.titulo[:80], pdf)
        return {"message": "Documento salvo no seu Google Drive.", **result}
    except GoogleNotConnected as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=502, detail="Erro ao salvar no Google Drive.")
