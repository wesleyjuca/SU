"""API de Notificações — listagem, marcação de leitura e remoção."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _serialize(n) -> dict:
    return {
        "id": str(n.id),
        "tipo": n.tipo,
        "titulo": n.titulo,
        "corpo": n.corpo,
        "lida": n.lida,
        "priority": n.priority,
        "link": n.link,
        "metadata": n.metadata,
        "created_at": n.created_at.isoformat(),
        "read_at": n.read_at.isoformat() if n.read_at else None,
    }


@router.get("")
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notifications = await notification_service.get_user_notifications(
        db, current_user.id, unread_only=unread_only, limit=limit
    )
    unread_count = await notification_service.get_unread_count(db, current_user.id)
    return {
        "unread_count": unread_count,
        "total": len(notifications),
        "items": [_serialize(n) for n in notifications],
    }


@router.patch("/{notification_id}/read")
async def mark_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notif = await notification_service.mark_read(db, notification_id, current_user.id)
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificação não encontrada")
    return _serialize(notif)


@router.post("/mark-all-read")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = await notification_service.mark_all_read(db, current_user.id)
    return {"updated": count}


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deleted = await notification_service.delete_notification(db, notification_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificação não encontrada")
