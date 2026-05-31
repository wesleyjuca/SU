"""Serviço de Web Push (VAPID) — sem dependências de conta externa."""
import json
import structlog

log = structlog.get_logger()


async def send_push(
    endpoint: str,
    p256dh: str,
    auth: str,
    title: str,
    body: str,
    url: str = "/dashboard",
) -> bool:
    """Envia push notification via VAPID. Retorna False se PUSH_ENABLED=False ou falha."""
    from app.config import settings
    if not settings.PUSH_ENABLED or not settings.VAPID_PRIVATE_KEY or not settings.VAPID_PUBLIC_KEY:
        return False

    try:
        from pywebpush import webpush

        payload = json.dumps({
            "title": title,
            "body": body,
            "url": url,
            "icon": "/icons/icon-192.png",
            "badge": "/icons/icon-192.png",
        })

        webpush(
            subscription_info={
                "endpoint": endpoint,
                "keys": {"p256dh": p256dh, "auth": auth},
            },
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_EMAIL},
        )
        log.info("push_sent", endpoint=endpoint[:50], title=title)
        return True

    except Exception as exc:
        # Handle 410 Gone separately — subscription expired, should be removed
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 410:
            log.info("push_subscription_expired", endpoint=endpoint[:50])
        else:
            log.warning("push_failed", endpoint=endpoint[:50], error=str(exc))
        return False


async def send_push_to_user(user_id: str, title: str, body: str, url: str = "/dashboard") -> int:
    """Envia push para todas as subscriptions ativas de um usuário. Retorna nº de envios."""
    from app.db.base import AsyncSessionLocal
    from app.models.push_subscription import PushSubscription
    from sqlalchemy import select
    import uuid

    sent = 0
    expired = []

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PushSubscription).where(PushSubscription.user_id == uuid.UUID(str(user_id)))
        )
        subs = result.scalars().all()

        for sub in subs:
            ok = await send_push(sub.endpoint, sub.p256dh, sub.auth, title, body, url)
            if ok:
                sent += 1
            else:
                # Check if expired (410) — mark for removal
                from app.config import settings
                if settings.PUSH_ENABLED:
                    expired.append(sub.id)

        # Remove expired subscriptions
        for sub_id in expired:
            sub_obj = await db.get(PushSubscription, sub_id)
            if sub_obj:
                await db.delete(sub_obj)
        if expired:
            await db.commit()

    return sent
