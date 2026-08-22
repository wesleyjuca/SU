"""Fase 205.5 — POST /system/ai-budget/request-increase: o usuário bloqueado
pelo teto mensal de IA (429 de enforce_budget) pode pedir um aumento direto
pela tela, notificando ADMIN/SÓCIO/SUPERADMIN do escritório em vez do fluxo
manual anterior. Postgres real (não mock) — 2 tenants, pra confirmar que a
notificação só alcança gestores do MESMO tenant do solicitante."""
import uuid

import pytest
from fastapi import HTTPException

from app.api.v1.system import request_ai_budget_increase
from app.db.base import AsyncSessionLocal
from app.models.notification import Notification
from app.models.tenant import Tenant
from app.models.user import AIBudgetLimit, User

pytestmark = pytest.mark.asyncio


class _CurrentUser:
    def __init__(self, user_id, tenant_id, full_name="Usuário Teste"):
        self.id = user_id
        self.tenant_id = tenant_id
        self.full_name = full_name


@pytest.fixture
async def cenario():
    async with AsyncSessionLocal() as db:
        tenant_a = Tenant(name="Tenant A 205.5", slug=f"teste-205-5-a-{uuid.uuid4().hex[:8]}")
        tenant_b = Tenant(name="Tenant B 205.5", slug=f"teste-205-5-b-{uuid.uuid4().hex[:8]}")
        db.add_all([tenant_a, tenant_b])
        await db.flush()

        advogado = User(
            email=f"adv-205-5-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Advogado Bloqueado", role="ADVOGADO", tenant_id=tenant_a.id,
        )
        admin_a = User(
            email=f"admin-205-5-a-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Admin A", role="ADMIN", tenant_id=tenant_a.id,
        )
        admin_b = User(
            email=f"admin-205-5-b-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Admin B", role="ADMIN", tenant_id=tenant_b.id,
        )
        db.add_all([advogado, admin_a, admin_b])
        await db.flush()

        db.add(AIBudgetLimit(
            user_id=advogado.id, tenant_id=tenant_a.id, monthly_limit_usd=10.0, alert_pct=80,
        ))
        await db.commit()

        ids = {
            "tenant_a": tenant_a.id, "tenant_b": tenant_b.id,
            "advogado": advogado.id, "admin_a": admin_a.id, "admin_b": admin_b.id,
        }
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(Notification.__table__.delete().where(
            Notification.user_id.in_([ids["advogado"], ids["admin_a"], ids["admin_b"]])
        ))
        await db.execute(AIBudgetLimit.__table__.delete().where(AIBudgetLimit.user_id == ids["advogado"]))
        await db.execute(User.__table__.delete().where(
            User.id.in_([ids["advogado"], ids["admin_a"], ids["admin_b"]])
        ))
        await db.execute(Tenant.__table__.delete().where(
            Tenant.id.in_([ids["tenant_a"], ids["tenant_b"]])
        ))
        await db.commit()


async def test_sem_teto_configurado_retorna_422():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant sem teto 205.5", slug=f"teste-205-5-c-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        user = User(
            email=f"sem-teto-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Sem Teto", role="ADVOGADO", tenant_id=tenant.id,
        )
        db.add(user)
        await db.flush()

        with pytest.raises(HTTPException) as exc:
            await request_ai_budget_increase(current_user=_CurrentUser(user.id, tenant.id), db=db)
        assert exc.value.status_code == 422
        # nunca commita — rollback ao fechar o `async with`


async def test_notifica_apenas_gestores_do_mesmo_tenant(cenario):
    ids = cenario
    async with AsyncSessionLocal() as db:
        resultado = await request_ai_budget_increase(
            current_user=_CurrentUser(ids["advogado"], ids["tenant_a"], "Fulano de Tal"), db=db,
        )
        assert "enviada" in resultado["message"].lower()

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        notifs_admin_a = (await db.execute(
            select(Notification).where(Notification.user_id == ids["admin_a"])
        )).scalars().all()
        notifs_admin_b = (await db.execute(
            select(Notification).where(Notification.user_id == ids["admin_b"])
        )).scalars().all()

    assert len(notifs_admin_a) == 1
    assert "Fulano de Tal" in notifs_admin_a[0].titulo
    assert notifs_admin_a[0].link == "/custos-ia"
    assert notifs_admin_b == [], "admin de OUTRO tenant não deveria ser notificado"


async def test_segunda_solicitacao_no_mesmo_dia_nao_duplica_notificacao(cenario):
    ids = cenario
    async with AsyncSessionLocal() as db:
        await request_ai_budget_increase(current_user=_CurrentUser(ids["advogado"], ids["tenant_a"]), db=db)

    async with AsyncSessionLocal() as db:
        resultado2 = await request_ai_budget_increase(
            current_user=_CurrentUser(ids["advogado"], ids["tenant_a"]), db=db,
        )
    assert "já solicitou" in resultado2["message"].lower()

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        notifs = (await db.execute(
            select(Notification).where(Notification.user_id == ids["admin_a"])
        )).scalars().all()
    assert len(notifs) == 1, "2ª solicitação no mesmo dia não deveria gerar outra notificação"
