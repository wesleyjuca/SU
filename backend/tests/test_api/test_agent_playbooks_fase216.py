"""Fase 216 (6ª proposta de evolução da Fase 209) — playbooks de agentes
por área: GET/POST/DELETE /playbooks. Postgres real: confirma upsert
(revisar a orientação de uma área atualiza em vez de duplicar), lista
retorna todas as áreas do tenant, isolamento cross-tenant e delete."""
import uuid

import pytest

from app.api.v1.playbooks import create_or_update_playbook, list_playbooks, delete_playbook, PlaybookCreate
from app.db.base import AsyncSessionLocal
from app.models.agent_playbook import AgentAreaPlaybook
from app.models.tenant import Tenant

pytestmark = pytest.mark.anyio


class _CurrentUser:
    def __init__(self, tenant_id, uid=None):
        self.tenant_id = tenant_id
        self.id = uid or uuid.uuid4()


@pytest.fixture
async def cenario():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 216", slug=f"teste-216-{uuid.uuid4().hex[:8]}")
        outro_tenant = Tenant(name="Outro 216", slug=f"outro-216-{uuid.uuid4().hex[:8]}")
        db.add_all([tenant, outro_tenant])
        await db.commit()
        ids = {"tenant": tenant.id, "outro_tenant": outro_tenant.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(AgentAreaPlaybook.__table__.delete().where(
            AgentAreaPlaybook.tenant_id.in_([ids["tenant"], ids["outro_tenant"]])
        ))
        await db.execute(Tenant.__table__.delete().where(Tenant.id.in_([ids["tenant"], ids["outro_tenant"]])))
        await db.commit()


async def test_create_e_lista(cenario):
    async with AsyncSessionLocal() as db:
        resp = await create_or_update_playbook(
            PlaybookCreate(area_direito="CIVIL", texto="Sempre checar prescrição."),
            current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    assert resp["area_direito"] == "CIVIL"

    async with AsyncSessionLocal() as db:
        playbooks = await list_playbooks(current_user=_CurrentUser(cenario["tenant"]), db=db)
    assert len(playbooks) == 1
    assert playbooks[0]["texto"] == "Sempre checar prescrição."


async def test_post_repetido_faz_upsert_nao_duplica(cenario):
    async with AsyncSessionLocal() as db:
        await create_or_update_playbook(
            PlaybookCreate(area_direito="CIVIL", texto="v1"),
            current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    async with AsyncSessionLocal() as db:
        await create_or_update_playbook(
            PlaybookCreate(area_direito="CIVIL", texto="v2"),
            current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    async with AsyncSessionLocal() as db:
        playbooks = await list_playbooks(current_user=_CurrentUser(cenario["tenant"]), db=db)
    assert len(playbooks) == 1
    assert playbooks[0]["texto"] == "v2"


async def test_lista_de_outro_tenant_nao_aparece(cenario):
    async with AsyncSessionLocal() as db:
        await create_or_update_playbook(
            PlaybookCreate(area_direito="CIVIL", texto="x"),
            current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    async with AsyncSessionLocal() as db:
        playbooks_outro = await list_playbooks(current_user=_CurrentUser(cenario["outro_tenant"]), db=db)
    assert playbooks_outro == []


async def test_delete_remove_playbook(cenario):
    async with AsyncSessionLocal() as db:
        criado = await create_or_update_playbook(
            PlaybookCreate(area_direito="PENAL", texto="x"),
            current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    async with AsyncSessionLocal() as db:
        await delete_playbook(criado["id"], current_user=_CurrentUser(cenario["tenant"]), db=db)
    async with AsyncSessionLocal() as db:
        playbooks = await list_playbooks(current_user=_CurrentUser(cenario["tenant"]), db=db)
    assert playbooks == []
