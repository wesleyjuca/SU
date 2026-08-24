"""Task Celery: desativa o User técnico de acessos ao Portal do Cliente
vencidos (Fase 234).

A garantia de segurança em si já é o check ao vivo em
`get_portal_client()` (`app/api/v1/portal.py`) — expira no instante
exato, não depende desta task rodar. Esta task é higiene: mantém
`User.is_active` consistente com `ClientPortalAccess.expires_at` pra
quem inspecionar a tabela diretamente, mesmo espírito de
`session_cleanup.py`.
"""
from app.workers.worker import celery_app
import structlog

log = structlog.get_logger()


@celery_app.task(
    name="app.workers.tasks.client_portal_access_reaper.desativar_portal_access_vencidos", bind=True,
    time_limit=600, soft_time_limit=480,
)
def desativar_portal_access_vencidos(self):
    from app.workers.async_utils import run_worker_coro

    async def _run():
        from datetime import datetime, timezone
        from sqlalchemy import select
        from app.db.base import AsyncSessionLocal
        from app.models.user import User
        from app.models.client import ClientPortalAccess

        async with AsyncSessionLocal() as db:
            vencidos = (await db.execute(
                select(ClientPortalAccess).where(
                    ClientPortalAccess.expires_at < datetime.now(timezone.utc),
                    ClientPortalAccess.revoked_at.is_(None),
                )
            )).scalars().all()
            desativados = 0
            for access in vencidos:
                user = (await db.execute(
                    select(User).where(User.id == access.portal_user_id, User.is_active.is_(True))
                )).scalar_one_or_none()
                if user:
                    user.is_active = False
                    desativados += 1
            await db.commit()
            log.info("client_portal_access_reaper", vencidos=len(vencidos), desativados=desativados)
            return {"vencidos": len(vencidos), "desativados": desativados}

    async def _run_with_lock():
        from app.workers.task_lock import TaskLock

        lock = TaskLock("desativar_portal_access_vencidos", ttl_seconds=900)
        if not await lock.acquire():
            log.info("task_skipped_lock_held", task="desativar_portal_access_vencidos")
            return {"skipped": True, "reason": "lock_held"}
        try:
            return await _run()
        finally:
            await lock.release()

    return run_worker_coro(_run_with_lock())
