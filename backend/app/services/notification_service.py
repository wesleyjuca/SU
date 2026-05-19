"""Serviço de notificações — criação, listagem e marcação de leitura."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification

log = structlog.get_logger()

TIPOS_VALIDOS = {
    "PRAZO_VENCENDO",
    "NOVO_ANDAMENTO",
    "APROVACAO_PENDENTE",
    "AGENTE_CONCLUIDO",
    "SISTEMA",
}


async def create_notification(
    db: AsyncSession,
    user_id: uuid.UUID,
    titulo: str,
    tipo: str = "SISTEMA",
    corpo: Optional[str] = None,
    priority: str = "NORMAL",
    link: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Notification:
    notif = Notification(
        user_id=user_id,
        tipo=tipo if tipo in TIPOS_VALIDOS else "SISTEMA",
        titulo=titulo[:255],
        corpo=corpo,
        priority=priority,
        link=link,
        metadata=metadata or {},
    )
    db.add(notif)
    await db.commit()
    await db.refresh(notif)
    log.info("notification_created", user_id=str(user_id), tipo=tipo)
    return notif


async def create_batch(
    db: AsyncSession,
    user_ids: list[uuid.UUID],
    titulo: str,
    tipo: str = "SISTEMA",
    corpo: Optional[str] = None,
    priority: str = "NORMAL",
    link: Optional[str] = None,
) -> int:
    """Cria a mesma notificação para múltiplos usuários."""
    count = 0
    for uid in user_ids:
        notif = Notification(
            user_id=uid,
            tipo=tipo if tipo in TIPOS_VALIDOS else "SISTEMA",
            titulo=titulo[:255],
            corpo=corpo,
            priority=priority,
            link=link,
        )
        db.add(notif)
        count += 1
    await db.commit()
    log.info("notifications_batch_created", count=count, tipo=tipo)
    return count


async def get_user_notifications(
    db: AsyncSession,
    user_id: uuid.UUID,
    unread_only: bool = False,
    limit: int = 50,
) -> list[Notification]:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(Notification.lida == False)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    from sqlalchemy import func
    result = await db.execute(
        select(func.count(Notification.id))
        .where(Notification.user_id == user_id, Notification.lida == False)
    )
    return result.scalar_one()


async def mark_read(
    db: AsyncSession,
    notification_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Optional[Notification]:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        return None
    notif.lida = True
    notif.read_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(notif)
    return notif


async def mark_all_read(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.lida == False)
        .values(lida=True, read_at=datetime.now(timezone.utc))
    )
    await db.commit()
    return result.rowcount


async def delete_notification(
    db: AsyncSession,
    notification_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        return False
    await db.delete(notif)
    await db.commit()
    return True
