"""Programa de Integridade — Código de Conduta (com aceite) e Canal de Denúncias."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from pydantic import BaseModel
import uuid
from datetime import datetime, timezone

from app.db.base import get_db
from app.dependencies import get_current_user, require_role
from app.models.user import User
from app.models.integrity import ConductAcceptance, IntegrityReport
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/integrity", tags=["integrity"])

CATEGORIAS_DENUNCIA = ["ETICA", "CONFLITO_INTERESSES", "DADOS_LGPD", "USO_DE_IA", "ASSEDIO", "OUTROS"]

# ─── Código de Conduta ────────────────────────────────────────────────────────
# O texto/versão vive em TenantConfig.document_templates["code_of_conduct"]
# (JSONB existente — sem migração). Aceites ficam em conduct_acceptances.


async def _get_conduct(db: AsyncSession, current_user: User) -> dict:
    from app.api.v1.tenant import _get_or_create_config
    _tenant, config = await _get_or_create_config(db, current_user)
    return (config.document_templates or {}).get("code_of_conduct", {})


@router.get("/conduct")
async def get_conduct(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Código de Conduta vigente + status de aceite do usuário atual."""
    conduct = await _get_conduct(db, current_user)
    version = int(conduct.get("version") or 0)
    accepted_at = None
    if version:
        row = (await db.execute(
            select(ConductAcceptance).where(
                ConductAcceptance.user_id == current_user.id,
                ConductAcceptance.version == version,
            )
        )).scalar_one_or_none()
        accepted_at = row.accepted_at.isoformat() if row else None
    return {
        "text": conduct.get("text") or "",
        "version": version,
        "updated_at": conduct.get("updated_at"),
        "accepted": bool(accepted_at),
        "accepted_at": accepted_at,
    }


class ConductUpdate(BaseModel):
    text: str


@router.put("/conduct")
async def update_conduct(
    body: ConductUpdate,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Salva o Código de Conduta e incrementa a versão (todos precisam re-aceitar)."""
    from app.api.v1.tenant import _get_or_create_config
    from app.core.tenant import invalidate_tenant_cache, DEFAULT_TENANT_SLUG

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="O texto do código não pode ser vazio.")

    tenant, config = await _get_or_create_config(db, current_user)
    templates = dict(config.document_templates or {})
    prev = templates.get("code_of_conduct", {})
    templates["code_of_conduct"] = {
        "text": text,
        "version": int(prev.get("version") or 0) + 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    config.document_templates = templates
    await db.flush()
    await invalidate_tenant_cache(getattr(tenant, "slug", None) or DEFAULT_TENANT_SLUG)
    return {"message": "Código de Conduta publicado", "version": templates["code_of_conduct"]["version"]}


@router.post("/conduct/accept", status_code=201)
async def accept_conduct(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Registra o aceite do usuário à versão vigente do Código de Conduta."""
    conduct = await _get_conduct(db, current_user)
    version = int(conduct.get("version") or 0)
    if not version:
        raise HTTPException(status_code=422, detail="Nenhum Código de Conduta publicado ainda.")

    existing = (await db.execute(
        select(ConductAcceptance).where(
            ConductAcceptance.user_id == current_user.id,
            ConductAcceptance.version == version,
        )
    )).scalar_one_or_none()
    if existing:
        return {"message": "Aceite já registrado", "version": version}

    db.add(ConductAcceptance(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        version=version,
    ))
    await db.flush()
    return {"message": "Aceite registrado", "version": version}


@router.get("/conduct/acceptances")
async def list_acceptances(
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    """Painel do aceite: quem já aceitou a versão vigente (tenant-scoped)."""
    conduct = await _get_conduct(db, current_user)
    version = int(conduct.get("version") or 0)

    total_users = (await db.execute(
        select(func.count(User.id)).where(
            User.tenant_id == current_user.tenant_id,
            User.is_active == True,  # noqa: E712
        )
    )).scalar_one() or 0

    rows = []
    if version:
        rows = (await db.execute(
            select(ConductAcceptance, User.full_name, User.email)
            .join(User, User.id == ConductAcceptance.user_id)
            .where(
                ConductAcceptance.tenant_id == current_user.tenant_id,
                ConductAcceptance.version == version,
            )
            .order_by(desc(ConductAcceptance.accepted_at))
        )).all()

    return {
        "version": version,
        "total_usuarios_ativos": int(total_users),
        "total_aceites": len(rows),
        "aceites": [
            {"nome": r.full_name, "email": r.email, "accepted_at": r.ConductAcceptance.accepted_at.isoformat()}
            for r in rows
        ],
    }


# ─── Canal de Denúncias ───────────────────────────────────────────────────────
class ReportCreate(BaseModel):
    categoria: str
    descricao: str
    anonimo: bool = False


class ReportResolve(BaseModel):
    status: str | None = None       # ABERTO, EM_ANALISE, RESOLVIDO
    resolucao: str | None = None


def _report_to_dict(r: IntegrityReport) -> dict:
    return {
        "id": str(r.id),
        "categoria": r.categoria,
        "descricao": r.descricao,
        "anonimo": r.anonimo,
        "status": r.status,
        "resolucao": r.resolucao,
        "created_at": r.created_at.isoformat(),
    }


@router.post("/reports", status_code=201)
async def create_report(
    body: ReportCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Registra um relato. Se anônimo, o autor NÃO é gravado no banco."""
    if body.categoria not in CATEGORIAS_DENUNCIA:
        raise HTTPException(status_code=422, detail=f"Categoria inválida. Use: {', '.join(CATEGORIAS_DENUNCIA)}")
    if not body.descricao.strip():
        raise HTTPException(status_code=422, detail="Descreva o relato.")

    report = IntegrityReport(
        tenant_id=current_user.tenant_id,
        categoria=body.categoria,
        descricao=body.descricao.strip(),
        anonimo=body.anonimo,
        created_by=None if body.anonimo else current_user.id,
    )
    db.add(report)
    await db.flush()
    return {
        "id": str(report.id),
        "protocolo": str(report.id)[:8].upper(),
        "message": "Relato registrado com confidencialidade. Guarde o protocolo para acompanhamento.",
    }


@router.get("/reports")
async def list_reports(
    status: str | None = None,
    limit: int = Query(default=100, le=200),
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    """Relatos do escritório (ADMIN/SÓCIO). Autor de relato anônimo nunca é exposto."""
    query = (
        select(IntegrityReport)
        .where(IntegrityReport.tenant_id == current_user.tenant_id)
        .order_by(desc(IntegrityReport.created_at))
        .limit(limit)
    )
    if status:
        query = query.where(IntegrityReport.status == status)
    rows = (await db.execute(query)).scalars().all()
    return [_report_to_dict(r) for r in rows]


@router.put("/reports/{report_id}")
async def resolve_report(
    report_id: str,
    body: ReportResolve,
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    """Atualiza status/resolução de um relato (tenant-scoped)."""
    report = (await db.execute(
        select(IntegrityReport).where(
            IntegrityReport.id == uuid.UUID(report_id),
            IntegrityReport.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if not report:
        raise NotFoundError("Relato", report_id)

    if body.status:
        if body.status not in ("ABERTO", "EM_ANALISE", "RESOLVIDO"):
            raise HTTPException(status_code=422, detail="Status inválido (ABERTO | EM_ANALISE | RESOLVIDO)")
        report.status = body.status
        if body.status == "RESOLVIDO":
            report.resolved_by = current_user.id
    if body.resolucao is not None:
        report.resolucao = body.resolucao.strip() or None
    await db.flush()
    return _report_to_dict(report)
