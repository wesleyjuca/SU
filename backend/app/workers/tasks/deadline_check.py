"""Tasks Celery: verificação de prazos e scan de publicações."""
from app.workers.worker import celery_app
import structlog

log = structlog.get_logger()


@celery_app.task(
    name="app.workers.tasks.deadline_check.check_upcoming_deadlines", bind=True,
    time_limit=1800, soft_time_limit=1500,
)
def check_upcoming_deadlines(self):
    """Verifica prazos nos próximos 3, 7 e 15 dias e envia notificações."""
    from app.workers.async_utils import run_worker_coro

    async def _run():
        from datetime import date, timedelta
        from sqlalchemy import select
        from app.db.base import AsyncSessionLocal
        from app.models.process import ProcessDeadline
        from app.models.notification import Notification
        from app.services.notification import publish_notification_ws, deve_notificar

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

                if not await deve_notificar(db, prazo.responsavel_id, "PRAZO_VENCENDO"):
                    # Fase 206.2 — usuário desativou "novos prazos". Ainda marca
                    # as faixas cruzadas (evita reprocessar o mesmo prazo todo
                    # dia só porque o alerta está desligado).
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
                await publish_notification_ws(notif)
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
                        tenant_id=user.tenant_id,
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
            # Fase 146 — janela + faixas já notificadas (alertas_enviados),
            # mesmo padrão do bloco de ProcessDeadline acima: evita reenvio em
            # execução duplicada/concorrente do job diário (o job não tem
            # run-mutex — 2 execuções no mesmo dia reenviariam e-mail/push/
            # WhatsApp pra todo contrato vencendo, antes desta fase) e torna
            # o alerta resiliente a downtime do worker (não depende de bater
            # a data exata).
            from sqlalchemy import func as _func
            from app.models.document import Contract, Document
            CONTRATO_BUCKETS = [30, 15, 7]
            contratos_notif = 0
            rows = (await db.execute(
                select(Contract, Document.created_by, Document.titulo)
                .join(Document, Contract.document_id == Document.id)
                .where(
                    Contract.data_fim.isnot(None),
                    _func.date(Contract.data_fim) >= today,
                    _func.date(Contract.data_fim) <= today + timedelta(days=max(CONTRATO_BUCKETS)),
                    Contract.status.notin_(["RASCUNHO", "CANCELADO", "ENCERRADO"]),
                )
            )).all()
            for contrato, created_by, titulo in rows:
                dias = (contrato.data_fim.date() - today).days
                enviados = set(contrato.alertas_enviados or [])
                aplicaveis = [b for b in CONTRATO_BUCKETS if dias <= b]
                nao_enviados = [b for b in aplicaveis if b not in enviados]
                if not nao_enviados or not created_by:
                    if aplicaveis and set(aplicaveis) - enviados:
                        contrato.alertas_enviados = sorted(enviados | set(aplicaveis))
                    continue

                if not await deve_notificar(db, created_by, "CONTRATO_VENCENDO"):
                    # Fase 206.2 — mesmo tipo de opt-out de "novos prazos".
                    contrato.alertas_enviados = sorted(enviados | set(aplicaveis))
                    continue

                sufixo = " (renovação automática)" if contrato.renovacao_auto else ""
                notif_contrato = Notification(
                    user_id=created_by,
                    tipo="CONTRATO_VENCENDO",
                    titulo=f"Contrato vence em {dias} dias: {(titulo or 'Contrato')[:70]}",
                    corpo=f"Vencimento: {contrato.data_fim.date()}{sufixo}",
                    priority="HIGH" if dias <= 7 else "NORMAL",
                    link="/contratos",
                )
                db.add(notif_contrato)
                await publish_notification_ws(notif_contrato)
                contratos_notif += 1
                contrato.alertas_enviados = sorted(enviados | set(aplicaveis))
            total_notificacoes += contratos_notif

            await db.commit()
            log.info("deadlines_checked", total_notificacoes=total_notificacoes, contratos=contratos_notif)
            return {"notificacoes_criadas": total_notificacoes, "contratos": contratos_notif}

    async def _run_with_lock():
        from app.workers.task_lock import TaskLock

        lock = TaskLock("check_upcoming_deadlines", ttl_seconds=2100)
        if not await lock.acquire():
            log.info("task_skipped_lock_held", task="check_upcoming_deadlines")
            return {"skipped": True, "reason": "lock_held"}
        try:
            return await _run()
        finally:
            await lock.release()

    return run_worker_coro(_run_with_lock())


@celery_app.task(
    name="app.workers.tasks.deadline_check.scan_daily_publications", bind=True,
    time_limit=3600, soft_time_limit=3300,
)
def scan_daily_publications(self):
    """Scan diário de publicações nos DJes."""
    from app.workers.async_utils import run_worker_coro

    async def _run():
        from app.db.base import AsyncSessionLocal
        from app.services.dje_monitor import scan_publicacoes

        async with AsyncSessionLocal() as db:
            # Varre a Comunica/DJEN (pública) para todas as OABs monitoradas.
            return await scan_publicacoes(db, tenant_id=None, dias_retro=1)

    async def _run_with_lock():
        from app.workers.task_lock import TaskLock

        lock = TaskLock("scan_daily_publications", ttl_seconds=3900)
        if not await lock.acquire():
            log.info("task_skipped_lock_held", task="scan_daily_publications")
            return {"skipped": True, "reason": "lock_held"}
        try:
            return await _run()
        finally:
            await lock.release()

    return run_worker_coro(_run_with_lock())


@celery_app.task(
    name="app.workers.tasks.deadline_check.check_petition_followups", bind=True,
    time_limit=1200, soft_time_limit=1000,
)
def check_petition_followups(self):
    """Fase 205.1 — alerta quando uma petição protocolada não recebeu
    nenhum retorno da corte no prazo de acompanhamento configurado pelo
    usuário (`Document.follow_up_dias`, opt-in por documento). Mesmo padrão
    de dedup de faixa única já usado nos outros alertas deste arquivo, só
    que com 1 alerta (não múltiplas faixas) — depois de disparado, cabe ao
    advogado decidir o próximo passo (consultar o processo, reprotocolar
    etc.), o sistema só avisa, nunca age sozinho."""
    from app.workers.async_utils import run_worker_coro

    async def _run():
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import select
        from app.db.base import AsyncSessionLocal
        from app.models.document import Document
        from app.models.notification import Notification
        from app.rag.auto_ingest import _PETICAO_TIPOS
        from app.services.notification import publish_notification_ws

        async with AsyncSessionLocal() as db:
            agora = datetime.now(timezone.utc)
            rows = (await db.execute(
                select(Document).where(
                    Document.status == "PROTOCOLADO",
                    Document.tipo.in_(_PETICAO_TIPOS),
                    Document.follow_up_dias.isnot(None),
                    Document.protocolado_em.isnot(None),
                    Document.follow_up_alertado.is_(False),
                    Document.created_by.isnot(None),
                )
            )).scalars().all()

            total = 0
            for doc in rows:
                prazo_atingido = doc.protocolado_em + timedelta(days=doc.follow_up_dias)
                if agora < prazo_atingido:
                    continue
                dias_passados = (agora - doc.protocolado_em).days
                notif = Notification(
                    user_id=doc.created_by,
                    tenant_id=doc.tenant_id,
                    tipo="SISTEMA",
                    titulo=f"Sem retorno em {dias_passados} dias: {doc.titulo[:70]}",
                    corpo=(
                        f"A petição \"{doc.titulo}\" foi protocolada há {dias_passados} dias "
                        f"sem movimentação registrada — vale a pena consultar o andamento."
                    ),
                    priority="NORMAL",
                    link="/documentos",
                )
                db.add(notif)
                await publish_notification_ws(notif)
                doc.follow_up_alertado = True
                total += 1

            await db.commit()
            log.info("petition_followups_checked", total_alertas=total)
            return {"alertas_criados": total}

    async def _run_with_lock():
        from app.workers.task_lock import TaskLock

        lock = TaskLock("check_petition_followups", ttl_seconds=1500)
        if not await lock.acquire():
            log.info("task_skipped_lock_held", task="check_petition_followups")
            return {"skipped": True, "reason": "lock_held"}
        try:
            return await _run()
        finally:
            await lock.release()

    return run_worker_coro(_run_with_lock())
