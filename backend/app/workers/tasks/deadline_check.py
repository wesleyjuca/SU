"""Tasks Celery: verificação de prazos e scan de publicações."""
from app.workers.worker import celery_app
import structlog

log = structlog.get_logger()


@celery_app.task(name="app.workers.tasks.deadline_check.check_upcoming_deadlines", bind=True)
def check_upcoming_deadlines(self):
    """Verifica prazos nos próximos 3, 7 e 15 dias e envia notificações."""
    from app.workers.async_utils import run_worker_coro

    async def _run():
        from datetime import date, timedelta
        from sqlalchemy import select
        from app.db.base import AsyncSessionLocal
        from app.models.process import ProcessDeadline
        from app.models.notification import Notification

        async with AsyncSessionLocal() as db:
            today = date.today()
            BUCKETS = [15, 7, 3]  # faixas de alerta (maior → menor)
            total_notificacoes = 0

            # Janela única: todos os prazos PENDENTES que vencem de hoje até +15
            # dias. Assim o alerta não depende da data exata (resiliente a downtime)
            # e cada faixa é notificada UMA vez (registrada em alertas_enviados).
            result = await db.execute(
                select(ProcessDeadline).where(
                    ProcessDeadline.status == "PENDENTE",
                    ProcessDeadline.data_prazo >= today,
                    ProcessDeadline.data_prazo <= today + timedelta(days=max(BUCKETS)),
                )
            )
            prazos = result.scalars().all()

            for prazo in prazos:
                dias = (prazo.data_prazo - today).days
                enviados = set(prazo.alertas_enviados or [])
                aplicaveis = [b for b in BUCKETS if dias <= b]
                nao_enviados = [b for b in aplicaveis if b not in enviados]
                if not nao_enviados or not prazo.responsavel_id:
                    # Ainda marca as faixas cruzadas p/ não reprocessar sem responsável
                    if aplicaveis and set(aplicaveis) - enviados:
                        prazo.alertas_enviados = sorted(enviados | set(aplicaveis))
                    continue

                notif = Notification(
                    user_id=prazo.responsavel_id,
                    tipo="PRAZO_VENCENDO",
                    titulo=f"Prazo em {dias} dia{'s' if dias != 1 else ''}: {prazo.descricao[:80]}",
                    corpo=f"Prazo: {prazo.data_prazo} | Tipo: {prazo.tipo}",
                    priority="HIGH" if dias <= 3 else "NORMAL",
                    link=f"/processos/{prazo.process_id}",
                )
                db.add(notif)
                total_notificacoes += 1
                # Marca TODAS as faixas já cruzadas (evita reenvio diário)
                prazo.alertas_enviados = sorted(enviados | set(aplicaveis))

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
                        db=db,
                        sender_user_id=user.id,
                    )
                if user:
                    from app.services.webpush import send_push_to_user
                    await send_push_to_user(
                        user_id=str(user.id),
                        title=f"{'🚨 URGENTE' if dias <= 3 else '⚠️'} Prazo em {dias} dia{'s' if dias != 1 else ''}",
                        body=prazo.descricao[:100],
                        url=f"/processos/{prazo.process_id}",
                    )
                if user and user.telefone:
                    from app.services.whatsapp import enviar_whatsapp
                    await enviar_whatsapp(
                        db, user.tenant_id, user.telefone,
                        f"Prazo em {dias} dia{'s' if dias != 1 else ''} ({prazo.data_prazo}): {prazo.descricao[:120]}",
                    )

            # ── Vencimento de contratos (D-30/15/7) ──────────────────────────
            from sqlalchemy import func as _func
            from app.models.document import Contract, Document
            contratos_notif = 0
            for dias in (30, 15, 7):
                alvo = today + timedelta(days=dias)
                rows = (await db.execute(
                    select(Contract, Document.created_by, Document.titulo)
                    .join(Document, Contract.document_id == Document.id)
                    .where(
                        _func.date(Contract.data_fim) == alvo,
                        Contract.status.notin_(["RASCUNHO", "CANCELADO", "ENCERRADO"]),
                    )
                )).all()
                for contrato, created_by, titulo in rows:
                    if not created_by:
                        continue
                    sufixo = " (renovação automática)" if contrato.renovacao_auto else ""
                    db.add(Notification(
                        user_id=created_by,
                        tipo="CONTRATO_VENCENDO",
                        titulo=f"Contrato vence em {dias} dias: {(titulo or 'Contrato')[:70]}",
                        corpo=f"Vencimento: {contrato.data_fim.date() if contrato.data_fim else '—'}{sufixo}",
                        priority="HIGH" if dias <= 7 else "NORMAL",
                        link="/contratos",
                    ))
                    contratos_notif += 1
            total_notificacoes += contratos_notif

            await db.commit()
            log.info("deadlines_checked", total_notificacoes=total_notificacoes, contratos=contratos_notif)
            return {"notificacoes_criadas": total_notificacoes, "contratos": contratos_notif}

    return run_worker_coro(_run())


@celery_app.task(name="app.workers.tasks.deadline_check.scan_daily_publications", bind=True)
def scan_daily_publications(self):
    """Scan diário de publicações nos DJes."""
    from app.workers.async_utils import run_worker_coro

    async def _run():
        from app.db.base import AsyncSessionLocal
        from app.services.dje_monitor import scan_publicacoes

        async with AsyncSessionLocal() as db:
            # Varre a Comunica/DJEN (pública) para todas as OABs monitoradas.
            return await scan_publicacoes(db, tenant_id=None, dias_retro=1)

    return run_worker_coro(_run())
