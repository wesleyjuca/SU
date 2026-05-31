"""Endpoints de Web Push (VAPID) — subscribe/unsubscribe/chave pública."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import Optional

from app.db.base import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.push_subscription import PushSubscription

router = APIRouter(prefix="/push", tags=["push"])


class SubscribeBody(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    user_agent: Optional[str] = None


class UnsubscribeBody(BaseModel):
    endpoint: str


@router.get("/vapid-public-key")
async def get_vapid_public_key():
    """Retorna a chave pública VAPID para uso no frontend."""
    from app.config import settings
    if not settings.VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=503, detail="Push notifications não configuradas")
    return {"public_key": settings.VAPID_PUBLIC_KEY}


@router.post("/subscribe", status_code=201)
async def subscribe(
    body: SubscribeBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Registra ou atualiza uma PushSubscription para o usuário autenticado."""
    # Upsert: se endpoint já existe, atualiza p256dh e auth
    result = await db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.p256dh = body.p256dh
        existing.auth = body.auth
        existing.user_agent = body.user_agent
        await db.commit()
        return {"id": str(existing.id), "updated": True}

    sub = PushSubscription(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        endpoint=body.endpoint,
        p256dh=body.p256dh,
        auth=body.auth,
        user_agent=body.user_agent,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return {"id": str(sub.id), "updated": False}


@router.delete("/unsubscribe", status_code=204)
async def unsubscribe(
    body: UnsubscribeBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove uma PushSubscription do usuário autenticado."""
    await db.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint,
            PushSubscription.user_id == current_user.id,
        )
    )
    await db.commit()
