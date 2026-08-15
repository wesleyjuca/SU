"""Google Workspace do escritório — ações (Agenda, Drive) + status de leitura.

Fase 139: a conexão OAuth em si (connect/callback/disconnect) passou a ser
genérica, via o hub de integrações (`/integrations/hub/google_workspace/
oauth/*`, `app/api/v1/integrations_hub.py`) — mesmo mecanismo já usado por
Stripe Connect/Mercado Pago/Google Drive doutrina. Este router só guarda o
que é específico do Google Workspace: leitura de status (usada por
`agenda/page.tsx` e `documentos/page.tsx` pra decidir se mostram um botão
condicional — contrato de resposta preservado) e as 2 ações que realmente
usam o token (criar evento na Agenda, salvar documento no Drive)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import uuid

from app.db.base import get_db
from app.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/integrations/google", tags=["google"])

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


@router.get("/status")
async def google_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services import integration_hub
    enabled = await _google_enabled(db, current_user.tenant_id)
    integ = await integration_hub.get_integration(db, current_user.tenant_id, "google_workspace")
    return {
        "enabled": enabled,   # opt-in do escritório (decisão do ADMIN do tenant)
        "configured": integration_hub.is_oauth_configured("google_workspace"),
        "connected": bool(enabled and integ and integ.status == "CONECTADA" and integ.credentials_enc),
        "google_email": (integ.extra_data or {}).get("google_email") if integ else None,
    }


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
    """Cria o prazo/compromisso direto na Google Agenda do escritório."""
    from app.services.google_workspace import get_valid_token, calendar_create_event, GoogleNotConnected
    if not await _google_enabled(db, current_user.tenant_id):
        raise HTTPException(status_code=422, detail=_MODULE_DISABLED)
    try:
        token = await get_valid_token(db, current_user.tenant_id)
        inicio = f"{body.data}T{body.hora}:00-05:00"  # fuso do Acre (UTC-5)
        fim_h = f"{int(body.hora[:2]) + 1:02d}{body.hora[2:]}"
        fim = f"{body.data}T{fim_h}:00-05:00"
        result = await calendar_create_event(token, body.titulo, body.descricao or "", inicio, fim)
        return {"message": "Evento criado na Google Agenda do escritório.", **result}
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
    """Gera o PDF timbrado do documento e salva no Google Drive do escritório."""
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
            from app.services.letterhead import resolve_logo_data_url
            logo_data_url = await resolve_logo_data_url(cfg)
            if logo_data_url:
                letterhead["logo_data_url"] = logo_data_url
    except Exception:
        letterhead = None

    pdf = build_petition_pdf(
        title=doc.titulo,
        content_html=doc.conteudo_html or doc.conteudo_texto or "",
        metadata={"status": doc.status},
        letterhead=letterhead,
    )
    try:
        token = await get_valid_token(db, current_user.tenant_id)
        result = await drive_upload_pdf(token, doc.titulo[:80], pdf)
        return {"message": "Documento salvo no Google Drive do escritório.", **result}
    except GoogleNotConnected as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=502, detail="Erro ao salvar no Google Drive.")


@router.post("/drive-save-doc/{doc_id}", status_code=201)
async def save_document_as_google_doc(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fase 182 — salva o documento como Google Doc colaborável (não PDF): a
    Drive API converte o HTML automaticamente no upload, sob o mesmo escopo
    `drive.file` já concedido — sem timbrado (isso continua exclusivo do PDF
    baixado/protocolado, via `/drive-save`)."""
    from app.services.google_workspace import get_valid_token, drive_upload_doc, GoogleNotConnected
    from app.models.document import Document
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

    conteudo = doc.conteudo_html or "".join(f"<p>{linha}</p>" for linha in (doc.conteudo_texto or "").split("\n"))
    try:
        token = await get_valid_token(db, current_user.tenant_id)
        result = await drive_upload_doc(token, doc.titulo[:80], conteudo)
        meta = dict(doc.metadata_json or {})
        meta["google_doc_id"] = result.get("id")
        meta["google_doc_url"] = result.get("link")
        doc.metadata_json = meta
        await db.flush()
        return {"message": "Documento salvo como Google Doc no Drive do escritório.", **result}
    except GoogleNotConnected as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=502, detail="Erro ao salvar como Google Doc.")
