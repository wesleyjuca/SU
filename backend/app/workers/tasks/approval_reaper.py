"""Task Celery: escalona `Approval` PENDENTE vencida (Fase 191).

`Approval.expires_at` (setado em `create_approval_from_state`, Fase 191)
existia no model desde muito antes mas nada lia/escalava aprovações
esquecidas — uma aprovação parada tempo demais só dependia de alguém
lembrar de resolvê-la. Este reaper NUNCA aprova/rejeita sozinho — isso
violaria o invariante de segurança HITL (CLAUDE.md: a ação crítica só
ocorre após aprovação humana explícita). O único efeito é notificar
todos os gestores do escritório (ADMIN/SOCIO/SUPERADMIN, não só o
assignee original) — a decisão continua 100% humana.

Idempotente via `escalated_at`: uma Approval só é escalada uma vez, não
a cada rodada do reaper (roda periodicamente via Beat)."""
from datetime import datetime, timezone

from sqlalchemy import select
import structlog

from app.workers.worker import celery_app

log = structlog.get_logger()


async def executar_reaper_approvals(db) -> dict:
    """Notifica os gestores do escritório pra cada `Approval` PENDENTE cujo
    `expires_at` já passou e que ainda não foi escalada. Marca
    `escalated_at` pra não repetir a notificação na próxima rodada."""
    from app.models.agent_run import Approval
    from app.models.user import User
    from app.models.notification import Notification
    from app.services.notification import publish_notification_ws
    from app.api.v1.ws import publish_event

    agora = datetime.now(timezone.utc)
    vencidas = (await db.execute(
        select(Approval).where(
            Approval.status == "PENDENTE",
            Approval.expires_at.is_not(None),
            Approval.expires_at < agora,
            Approval.escalated_at.is_(None),
        )
    )).scalars().all()

    escaladas = 0
    for approval in vencidas:
        gestores = (await db.execute(
            select(User.id).where(
                User.tenant_id == approval.tenant_id,
                User.role.in_(["ADMIN", "SOCIO", "SUPERADMIN"]),
                User.is_active == True,  # noqa: E712
            )
        )).scalars().all()

        for uid in gestores:
            try:
                notif = Notification(
                    user_id=uid,
                    tipo="APROVACAO_PENDENTE",
                    titulo=f"Aprovação vencida sem decisão: {approval.titulo}",
                    corpo="Esta aprovação está pendente há mais tempo que o esperado e precisa de atenção.",
                    priority="HIGH",
                    link="/aprovacoes",
                )
                db.add(notif)
                await publish_notification_ws(notif)
            except Exception as exc:
                log.warning("approval_escalation_notify_failed", approval_id=str(approval.id), error=str(exc))
            await publish_event(str(uid), "NEW_APPROVAL_PENDING", {
                "approval_id": str(approval.id),
                "tipo": approval.tipo,
                "titulo": approval.titulo,
                "prioridade": approval.prioridade,
                "escalada": True,
            })

        approval.escalated_at = agora
        escaladas += 1

    if escaladas:
        await db.commit()
        log.warning("approvals_escaladas", quantidade=escaladas)

    return {"escaladas": escaladas}


@celery_app.task(
    name="app.workers.tasks.approval_reaper.escalar_aprovacoes_vencidas", bind=True, max_retries=3,
    time_limit=180, soft_time_limit=150,
)
def escalar_aprovacoes_vencidas(self):
    """Executa `executar_reaper_approvals()` — roda via Beat."""
    from app.workers.async_utils import run_worker_coro

    async def _run():
        from app.db.base import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            return await executar_reaper_approvals(db)

    async def _run_with_lock():
        from app.workers.task_lock import TaskLock

        lock = TaskLock("escalar_aprovacoes_vencidas", ttl_seconds=280)
        if not await lock.acquire():
            log.info("task_skipped_lock_held", task="escalar_aprovacoes_vencidas")
            return {"skipped": True, "reason": "lock_held"}
        try:
            return await _run()
        finally:
            await lock.release()

    try:
        return run_worker_coro(_run_with_lock())
    except Exception as exc:
        log.error("approval_reaper_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60)
