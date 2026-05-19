"""API de Auditoria — listagem e resumo de eventos do audit_log."""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.dependencies import require_role
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
async def list_audit_logs(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    agent_name: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
):
    stmt = select(AuditLog).order_by(AuditLog.timestamp.desc())

    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"%{action}%"))
    if success is not None:
        stmt = stmt.where(AuditLog.success == success)
    if agent_name:
        stmt = stmt.where(AuditLog.agent_name == agent_name)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)

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


@router.get("/summary")
async def audit_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
):
    by_action = await db.execute(
        select(AuditLog.action, func.count(AuditLog.id).label("total"))
        .group_by(AuditLog.action)
        .order_by(func.count(AuditLog.id).desc())
        .limit(20)
    )

    by_agent = await db.execute(
        select(AuditLog.agent_name, func.count(AuditLog.id).label("total"))
        .where(AuditLog.agent_name.isnot(None))
        .group_by(AuditLog.agent_name)
        .order_by(func.count(AuditLog.id).desc())
        .limit(20)
    )

    success_rate = await db.execute(
        select(
            func.count(AuditLog.id).label("total"),
            func.count(AuditLog.id).filter(AuditLog.success == True).label("successes"),
        )
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
