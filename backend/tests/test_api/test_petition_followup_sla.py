"""Fase 205.1 — Follow-up SLA em petições protocoladas: alerta quando uma
petição fica protocolada sem retorno da corte por `follow_up_dias` dias
(opt-in por documento). Postgres + Redis reais.

Cobre: (1) `protocolado_em` é carimbado uma única vez na transição pra
PROTOCOLADO e não se move em edições subsequentes; (2) uma reprotocolação
(saiu de PROTOCOLADO e voltou) recarimba `protocolado_em` e reseta
`follow_up_alertado`; (3) a task `check_petition_followups` só notifica
documentos que já cruzaram o prazo, ignora os que ainda não cruzaram, e é
idempotente (`follow_up_alertado` evita reenvio numa 2ª execução)."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import select

from app.api.v1.documents import DocumentUpdate, update_document
from app.db.base import AsyncSessionLocal
from app.models.document import Document
from app.models.notification import Notification
from app.models.tenant import Tenant
from app.models.user import User
from app.workers.tasks.deadline_check import check_petition_followups

pytestmark = pytest.mark.anyio


class _CurrentUser:
    def __init__(self, user_id, tenant_id):
        self.id = user_id
        self.tenant_id = tenant_id


@pytest.fixture
async def cenario():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 205.1", slug=f"teste-205-1-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        user = User(
            email=f"adv-205-1-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Advogado 205.1", role="ADVOGADO", tenant_id=tenant.id,
        )
        db.add(user)
        await db.commit()
        ids = {"tenant": tenant.id, "user": user.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(Notification.__table__.delete().where(Notification.user_id == ids["user"]))
        await db.execute(Document.__table__.delete().where(Document.tenant_id == ids["tenant"]))
        await db.execute(User.__table__.delete().where(User.id == ids["user"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == ids["tenant"]))
        await db.commit()


async def _criar_doc(tenant_id, user_id, **kwargs):
    doc = Document(
        tenant_id=tenant_id, created_by=user_id, titulo=kwargs.pop("titulo", "Petição de teste"),
        tipo="PETICAO", status="RASCUNHO", gerado_por_ia=False, **kwargs,
    )
    async with AsyncSessionLocal() as db:
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        return doc.id


async def test_protocolado_em_carimbado_uma_vez_e_nao_se_move_em_edicao_posterior(cenario):
    ids = cenario
    doc_id = await _criar_doc(ids["tenant"], ids["user"])

    async with AsyncSessionLocal() as db:
        resp = await update_document(
            str(doc_id), DocumentUpdate(status="PROTOCOLADO"), BackgroundTasks(),
            current_user=_CurrentUser(ids["user"], ids["tenant"]), db=db,
        )
        await db.commit()
    assert resp.protocolado_em is not None
    assert resp.follow_up_alertado is False
    primeiro_carimbo = resp.protocolado_em

    # Edição não relacionada ao status — protocolado_em não deve se mover.
    async with AsyncSessionLocal() as db:
        resp2 = await update_document(
            str(doc_id), DocumentUpdate(titulo="Petição de teste (revisada)"), BackgroundTasks(),
            current_user=_CurrentUser(ids["user"], ids["tenant"]), db=db,
        )
        await db.commit()
    assert resp2.protocolado_em == primeiro_carimbo


async def test_reprotocolar_recarimba_e_reseta_follow_up_alertado(cenario):
    ids = cenario
    doc_id = await _criar_doc(ids["tenant"], ids["user"])

    async with AsyncSessionLocal() as db:
        await update_document(
            str(doc_id), DocumentUpdate(status="PROTOCOLADO"), BackgroundTasks(),
            current_user=_CurrentUser(ids["user"], ids["tenant"]), db=db,
        )
        await db.commit()

    # Simula um alerta já disparado e o carimbo antigo.
    carimbo_antigo = datetime.now(timezone.utc) - timedelta(days=40)
    async with AsyncSessionLocal() as db:
        doc = (await db.execute(select(Document).where(Document.id == doc_id))).scalar_one()
        doc.follow_up_alertado = True
        doc.protocolado_em = carimbo_antigo
        await db.commit()

    # Sai de PROTOCOLADO e volta — mesmo padrão de "reprotocolar" após ajuste.
    async with AsyncSessionLocal() as db:
        await update_document(
            str(doc_id), DocumentUpdate(status="RASCUNHO"), BackgroundTasks(),
            current_user=_CurrentUser(ids["user"], ids["tenant"]), db=db,
        )
        await db.commit()
    async with AsyncSessionLocal() as db:
        resp = await update_document(
            str(doc_id), DocumentUpdate(status="PROTOCOLADO"), BackgroundTasks(),
            current_user=_CurrentUser(ids["user"], ids["tenant"]), db=db,
        )
        await db.commit()

    assert resp.follow_up_alertado is False
    assert resp.protocolado_em != carimbo_antigo.isoformat()


def _run_task_setup(coro):
    """Mesmo padrão de `run_worker_coro` (app/workers/async_utils.py): cada
    chamada roda em um event loop próprio e descarta o pool do engine ao
    final — sem isso, uma conexão asyncpg pooled de uma chamada sobrevive
    presa ao loop já fechado e a PRÓXIMA chamada (seja outro `asyncio.run()`
    daqui, seja o `asyncio.run()` interno de `check_petition_followups.run()`)
    explode com 'got Future attached to a different loop'."""
    async def _wrapped():
        try:
            return await coro
        finally:
            from app.db.base import engine
            await engine.dispose()

    return asyncio.run(_wrapped())


async def _preparar_task_scenario():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 205.1 task", slug=f"teste-205-1-task-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        user = User(
            email=f"adv-205-1-task-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Advogado Task 205.1", role="ADVOGADO", tenant_id=tenant.id,
        )
        db.add(user)
        await db.flush()

        marcador = uuid.uuid4().hex[:8]
        vencida = Document(
            tenant_id=tenant.id, created_by=user.id, titulo=f"Petição vencida {marcador}",
            tipo="PETICAO", status="PROTOCOLADO", gerado_por_ia=False,
            follow_up_dias=10, follow_up_alertado=False,
            protocolado_em=datetime.now(timezone.utc) - timedelta(days=15),
        )
        dentro_do_prazo = Document(
            tenant_id=tenant.id, created_by=user.id, titulo=f"Petição no prazo {marcador}",
            tipo="PETICAO", status="PROTOCOLADO", gerado_por_ia=False,
            follow_up_dias=10, follow_up_alertado=False,
            protocolado_em=datetime.now(timezone.utc) - timedelta(days=2),
        )
        db.add_all([vencida, dentro_do_prazo])
        await db.commit()
        await db.refresh(vencida)
        await db.refresh(dentro_do_prazo)
        return {
            "tenant": tenant.id, "user": user.id, "marcador": marcador,
            "vencida": vencida.id, "dentro_do_prazo": dentro_do_prazo.id,
        }


async def _limpar_task_scenario(ids):
    async with AsyncSessionLocal() as db:
        await db.execute(Notification.__table__.delete().where(Notification.user_id == ids["user"]))
        await db.execute(Document.__table__.delete().where(Document.tenant_id == ids["tenant"]))
        await db.execute(User.__table__.delete().where(User.id == ids["user"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == ids["tenant"]))
        await db.commit()


async def _estado_pos_execucao(ids):
    async with AsyncSessionLocal() as db:
        notifs = (await db.execute(
            select(Notification).where(Notification.user_id == ids["user"])
        )).scalars().all()
        vencida = (await db.execute(select(Document).where(Document.id == ids["vencida"]))).scalar_one()
        dentro = (await db.execute(select(Document).where(Document.id == ids["dentro_do_prazo"]))).scalar_one()
        return notifs, vencida, dentro


def test_check_petition_followups_alerta_so_quem_venceu_o_prazo_e_e_idempotente():
    """Sem @pytest.mark.asyncio de propósito: check_petition_followups.run()
    chama asyncio.run() internamente (run_worker_coro) — rodar isso dentro de
    um teste já async lançaria 'asyncio.run() cannot be called from a running
    event loop' (mesmo padrão de test_task_lock.py)."""
    ids = _run_task_setup(_preparar_task_scenario())
    try:
        resultado = check_petition_followups.run()
        assert resultado.get("skipped") is not True

        notifs, vencida, dentro = _run_task_setup(_estado_pos_execucao(ids))
        assert len(notifs) == 1, "só a petição vencida deveria gerar notificação"
        assert ids["marcador"] in notifs[0].titulo
        assert "vencida" in notifs[0].titulo.lower()
        assert notifs[0].link == "/documentos"
        assert vencida.follow_up_alertado is True
        assert dentro.follow_up_alertado is False, "petição ainda dentro do prazo não deveria ser alertada"

        # 2ª execução — follow_up_alertado já True na petição vencida, dedup.
        check_petition_followups.run()
        notifs2, _, _ = _run_task_setup(_estado_pos_execucao(ids))
        assert len(notifs2) == 1, "2ª execução não deveria duplicar a notificação (dedup por follow_up_alertado)"
    finally:
        _run_task_setup(_limpar_task_scenario(ids))
