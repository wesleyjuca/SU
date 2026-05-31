"""Tasks Celery: verificação de prazos e scan de publicações."""
from app.workers.worker import celery_app
import structlog

log = structlog.get_logger()


@celery_app.task(name="app.workers.tasks.deadline_check.check_upcoming_deadlines", bind=True)
def check_upcoming_deadlines(self):
    """Verifica prazos nos próximos 3, 7 e 15 dias e envia notificações."""
    import asyncio

    async def _run():
        from datetime import date, timedelta
        from sqlalchemy import select
        from app.db.base import AsyncSessionLocal
        from app.models.process import ProcessDeadline
        from app.models.notification import Notification

        async with AsyncSessionLocal() as db:
            today = date.today()
            alertas = [3, 7, 15]
            total_notificacoes = 0

            for dias in alertas:
                alvo = today + timedelta(days=dias)
                result = await db.execute(
                    select(ProcessDeadline).where(
                        ProcessDeadline.data_prazo == alvo,
                        ProcessDeadline.status == "PENDENTE",
                    )
                )
                prazos = result.scalars().all()

                for prazo in prazos:
                    if prazo.responsavel_id:
                        notif = Notification(
                            user_id=prazo.responsavel_id,
                            tipo="PRAZO_VENCENDO",
                            titulo=f"Prazo em {dias} dias: {prazo.descricao[:80]}",
                            corpo=f"Prazo: {prazo.data_prazo} | Tipo: {prazo.tipo}",
                            priority="HIGH" if dias <= 3 else "NORMAL",
                            link=f"/processos/{prazo.process_id}",
                        )
                        db.add(notif)
                        total_notificacoes += 1

                        # Tenta enviar email e push para o responsável
                        from app.models.user import User as UserModel
                        user_res = await db.execute(
                            select(UserModel).where(UserModel.id == prazo.responsavel_id)
                        )
                        user = user_res.scalar_one_or_none()
                        if user and user.email:
                            from app.services.email import send_prazo_alert
                            await send_prazo_alert(
                                to_email=user.email,
                                descricao=prazo.descricao,
                                dias=dias,
                                data_prazo=str(prazo.data_prazo),
                                process_id=str(prazo.process_id),
                            )
                        if user:
                            from app.services.webpush import send_push_to_user
                            await send_push_to_user(
                                user_id=str(user.id),
                                title=f"{'🚨 URGENTE' if dias <= 3 else '⚠️'} Prazo em {dias} dia{'s' if dias != 1 else ''}",
                                body=prazo.descricao[:100],
                                url=f"/processos/{prazo.process_id}",
                            )

            await db.commit()
            log.info("deadlines_checked", total_notificacoes=total_notificacoes)
            return {"notificacoes_criadas": total_notificacoes}

    return asyncio.run(_run())


@celery_app.task(name="app.workers.tasks.deadline_check.scan_daily_publications", bind=True)
def scan_daily_publications(self):
    """Scan diário de publicações nos DJes."""
    import asyncio

    async def _run():
        from app.db.base import AsyncSessionLocal
        from app.agents.publication_monitor.publication_monitor_agent import PublicationMonitorAgent
        from app.agents.brain.context import AgentContext
        from datetime import date

        async with AsyncSessionLocal() as db:
            agent = PublicationMonitorAgent(db=db)
            ctx = AgentContext(
                task_type="monitor_publications",
                task_input={"data": date.today().isoformat()},
            )
            result = await agent.run(ctx)
            return result.output

    return asyncio.run(_run())
