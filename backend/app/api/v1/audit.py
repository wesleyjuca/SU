"""API de Auditoria — listagem, resumo e exportação de eventos do audit_log."""
from datetime import date, datetime, time, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.dependencies import require_role
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter(prefix="/audit", tags=["audit"])


def _aplicar_filtros(stmt, tenant_id, action, success, agent_name, resource_type, date_from, date_to):
    stmt = stmt.where(AuditLog.tenant_id == tenant_id)
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"%{action}%"))
    if success is not None:
        stmt = stmt.where(AuditLog.success == success)
    if agent_name:
        stmt = stmt.where(AuditLog.agent_name == agent_name)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if date_from:
        stmt = stmt.where(AuditLog.timestamp >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        stmt = stmt.where(AuditLog.timestamp <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    return stmt


@router.get("")
async def list_audit_logs(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    agent_name: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
):
    stmt = _aplicar_filtros(
        select(AuditLog).order_by(AuditLog.timestamp.desc()),
        current_user.tenant_id, action, success, agent_name, resource_type, date_from, date_to,
    )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    result = await db.execute(stmt.offset(offset).limit(limit))
    logs = result.scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": log.id,
                "event_id": str(log.event_id),
                "timestamp": log.timestamp.isoformat(),
                "user_id": str(log.user_id) if log.user_id else None,
                "agent_name": log.agent_name,
                "run_id": str(log.run_id) if log.run_id else None,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": str(log.resource_id) if log.resource_id else None,
                "success": log.success,
                "contains_pii": log.contains_pii,
                "legal_basis": log.legal_basis,
                "ip_address": log.ip_address,
                "error_detail": log.error_detail,
            }
            for log in logs
        ],
    }


@router.get("/export")
async def export_audit_logs(
    action: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    agent_name: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
):
    """Exporta os eventos de auditoria (mesmos filtros de `GET /audit`) como
    CSV — self-service pra revisor de compliance/LGPD, sem precisar de
    acesso direto ao banco. Mesmo padrão de `GET /financial/export`."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    stmt = _aplicar_filtros(
        select(AuditLog).order_by(AuditLog.timestamp.desc()),
        current_user.tenant_id, action, success, agent_name, resource_type, date_from, date_to,
    ).limit(50_000)
    logs = (await db.execute(stmt)).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Data/Hora", "Usuário", "Agente", "Ação", "Tipo do recurso", "ID do recurso",
        "Sucesso", "Contém PII", "Base legal", "IP", "Erro",
    ])
    for log in logs:
        writer.writerow([
            log.timestamp.isoformat(),
            str(log.user_id) if log.user_id else "",
            log.agent_name or "",
            log.action,
            log.resource_type or "",
            str(log.resource_id) if log.resource_id else "",
            "sim" if log.success else "não",
            "sim" if log.contains_pii else "não",
            log.legal_basis or "",
            log.ip_address or "",
            log.error_detail or "",
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=auditoria.csv"},
    )


@router.get("/summary")
async def audit_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
):
    by_action = await db.execute(
        select(AuditLog.action, func.count(AuditLog.id).label("total"))
        .where(AuditLog.tenant_id == current_user.tenant_id)
        .group_by(AuditLog.action)
        .order_by(func.count(AuditLog.id).desc())
        .limit(20)
    )

    by_agent = await db.execute(
        select(AuditLog.agent_name, func.count(AuditLog.id).label("total"))
        .where(AuditLog.agent_name.isnot(None), AuditLog.tenant_id == current_user.tenant_id)
        .group_by(AuditLog.agent_name)
        .order_by(func.count(AuditLog.id).desc())
        .limit(20)
    )

    success_rate = await db.execute(
        select(
            func.count(AuditLog.id).label("total"),
            func.count(AuditLog.id).filter(AuditLog.success == True).label("successes"),
        ).where(AuditLog.tenant_id == current_user.tenant_id)
    )
    totals = success_rate.one()

    total_events = totals[0] or 0
    total_success = totals[1] or 0

    return {
        "total_events": total_events,
        "success_rate": round(total_success / total_events * 100, 1) if total_events else 0,
        "by_action": [{"action": r[0], "count": r[1]} for r in by_action],
        "by_agent": [{"agent": r[0], "count": r[1]} for r in by_agent],
    }
