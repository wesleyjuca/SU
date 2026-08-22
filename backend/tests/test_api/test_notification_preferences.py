"""Fase 206.2 — preferências de notificação persistentes por tipo de evento.
Postgres real: confirma que o endpoint persiste em `User.notification_prefs`
(antes só localStorage) e que `deve_notificar()`/`create_notification()`
realmente respeitam a preferência salva, não só a UI."""
import uuid

import pytest
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.models.notification import Notification
from app.models.tenant import Tenant
from app.models.user import User
from app.services.notification import create_notification, deve_notificar

pytestmark = pytest.mark.anyio


async def test_endpoint_persiste_e_le_de_volta(client, auth_headers):
    put_res = await client.put(
        "/api/v1/users/me/notification-preferences",
        json={"prefs": {"novos_prazos": False, "agente_concluiu": True}},
        headers=auth_headers,
    )
    assert put_res.status_code == 200

    get_res = await client.get("/api/v1/users/me/notification-preferences", headers=auth_headers)
    assert get_res.status_code == 200
    prefs = get_res.json()["prefs"]
    assert prefs["novos_prazos"] is False
    assert prefs["agente_concluiu"] is True

    # Restaura pro estado "opt-in" padrão pra não vazar preferência entre testes.
    await client.put(
        "/api/v1/users/me/notification-preferences",
        json={"prefs": {}},
        headers=auth_headers,
    )


@pytest.fixture
async def usuario_optout():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 206.2", slug=f"teste-206-2-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        user = User(
            email=f"adv-206-2-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Advogado 206.2", role="ADVOGADO", tenant_id=tenant.id,
            notification_prefs={"novos_prazos": False},
        )
        db.add(user)
        await db.commit()
        ids = {"tenant": tenant.id, "user": user.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(Notification.__table__.delete().where(Notification.user_id == ids["user"]))
        await db.execute(User.__table__.delete().where(User.id == ids["user"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == ids["tenant"]))
        await db.commit()


async def test_deve_notificar_respeita_opt_out_explicito(usuario_optout):
    async with AsyncSessionLocal() as db:
        assert await deve_notificar(db, usuario_optout["user"], "PRAZO_VENCENDO") is False
        # CONTRATO_VENCENDO compartilha a mesma pref key (novos_prazos).
        assert await deve_notificar(db, usuario_optout["user"], "CONTRATO_VENCENDO") is False
        # Tipo sem toggle na UI — sempre notifica, opt-out não alcança.
        assert await deve_notificar(db, usuario_optout["user"], "SISTEMA") is True
        # Tipo com toggle mas SEM opt-out (chave ausente) — default opt-in.
        assert await deve_notificar(db, usuario_optout["user"], "APROVACAO_PENDENTE") is True


async def test_create_notification_nao_cria_linha_quando_desativado(usuario_optout):
    async with AsyncSessionLocal() as db:
        resultado = await create_notification(
            db, usuario_optout["user"], "Prazo vencendo", tipo="PRAZO_VENCENDO",
        )
    assert resultado is None

    async with AsyncSessionLocal() as db:
        linhas = (await db.execute(
            select(Notification).where(Notification.user_id == usuario_optout["user"])
        )).scalars().all()
    assert linhas == []


async def test_create_notification_cria_normalmente_pra_tipo_nao_gateado(usuario_optout):
    async with AsyncSessionLocal() as db:
        resultado = await create_notification(
            db, usuario_optout["user"], "Aviso do sistema", tipo="SISTEMA",
        )
    assert resultado is not None

    async with AsyncSessionLocal() as db:
        linhas = (await db.execute(
            select(Notification).where(Notification.user_id == usuario_optout["user"])
        )).scalars().all()
    assert len(linhas) == 1
    assert linhas[0].tipo == "SISTEMA"
