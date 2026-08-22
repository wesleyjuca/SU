"""Fase 213 (3ª proposta de evolução da Fase 209) — metas de captação no
CRM: GET/POST/DELETE /crm/metas. Postgres real: confirma upsert (revisar a
meta no meio do período atualiza em vez de duplicar), cálculo de
`realizado` (só GANHO dentro do período conta), gate de escrita restrito a
ADMIN/SOCIO/GESTOR e isolamento cross-tenant."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.api.v1.crm import create_or_update_meta, list_metas, delete_meta, MetaCreate
from app.db.base import AsyncSessionLocal
from app.models.crm import CrmMeta, Opportunity
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.anyio

PERIODO = "2026-06"


class _CurrentUser:
    def __init__(self, tenant_id, uid=None):
        self.tenant_id = tenant_id
        self.id = uid or uuid.uuid4()


@pytest.fixture
async def cenario():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 213 CRM", slug=f"teste-213-{uuid.uuid4().hex[:8]}")
        outro_tenant = Tenant(name="Outro 213", slug=f"outro-213-{uuid.uuid4().hex[:8]}")
        db.add_all([tenant, outro_tenant])
        await db.flush()
        gestor = User(
            email=f"gestor-213-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Gestor Teste 213", role="GESTOR", tenant_id=tenant.id,
        )
        db.add(gestor)
        await db.flush()

        dentro = datetime(2026, 6, 15, tzinfo=timezone.utc)
        fora = datetime(2026, 5, 20, tzinfo=timezone.utc)
        opps = [
            Opportunity(titulo="Ganho dentro 1", valor_estimado=Decimal("10000"), estagio="GANHO",
                        tenant_id=tenant.id, updated_at=dentro),
            Opportunity(titulo="Ganho dentro 2", valor_estimado=Decimal("5000"), estagio="GANHO",
                        tenant_id=tenant.id, updated_at=dentro),
            Opportunity(titulo="Ganho fora do período", valor_estimado=Decimal("99999"), estagio="GANHO",
                        tenant_id=tenant.id, updated_at=fora),
            Opportunity(titulo="Aberta (não conta)", valor_estimado=Decimal("99999"), estagio="LEAD",
                        tenant_id=tenant.id, updated_at=dentro),
        ]
        db.add_all(opps)
        await db.commit()
        ids = {"tenant": tenant.id, "outro_tenant": outro_tenant.id, "gestor": gestor.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(CrmMeta.__table__.delete().where(CrmMeta.tenant_id.in_([ids["tenant"], ids["outro_tenant"]])))
        await db.execute(Opportunity.__table__.delete().where(Opportunity.tenant_id == ids["tenant"]))
        await db.execute(User.__table__.delete().where(User.id == ids["gestor"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id.in_([ids["tenant"], ids["outro_tenant"]])))
        await db.commit()


async def test_create_calcula_realizado_so_do_periodo(cenario):
    async with AsyncSessionLocal() as db:
        resp = await create_or_update_meta(
            MetaCreate(periodo=PERIODO, tipo="RECEITA", valor_meta=Decimal("20000")),
            current_user=_CurrentUser(cenario["tenant"], cenario["gestor"]), db=db,
        )
    async with AsyncSessionLocal() as db:
        metas = await list_metas(periodo=PERIODO, current_user=_CurrentUser(cenario["tenant"]), db=db)
    assert len(metas) == 1
    assert metas[0]["realizado"] == 15000.0  # só os 2 GANHO dentro do período
    assert metas[0]["percentual"] == 75.0
    assert resp["valor_meta"] == 20000.0


async def test_post_repetido_faz_upsert_nao_duplica(cenario):
    async with AsyncSessionLocal() as db:
        await create_or_update_meta(
            MetaCreate(periodo=PERIODO, tipo="RECEITA", valor_meta=Decimal("10000")),
            current_user=_CurrentUser(cenario["tenant"], cenario["gestor"]), db=db,
        )
    async with AsyncSessionLocal() as db:
        await create_or_update_meta(
            MetaCreate(periodo=PERIODO, tipo="RECEITA", valor_meta=Decimal("30000")),
            current_user=_CurrentUser(cenario["tenant"], cenario["gestor"]), db=db,
        )
    async with AsyncSessionLocal() as db:
        metas = await list_metas(periodo=PERIODO, current_user=_CurrentUser(cenario["tenant"]), db=db)
    assert len(metas) == 1
    assert metas[0]["valor_meta"] == 30000.0


async def test_novos_clientes_conta_quantidade(cenario):
    async with AsyncSessionLocal() as db:
        await create_or_update_meta(
            MetaCreate(periodo=PERIODO, tipo="NOVOS_CLIENTES", valor_meta=Decimal("5")),
            current_user=_CurrentUser(cenario["tenant"], cenario["gestor"]), db=db,
        )
    async with AsyncSessionLocal() as db:
        metas = await list_metas(periodo=PERIODO, current_user=_CurrentUser(cenario["tenant"]), db=db)
    assert metas[0]["realizado"] == 2.0  # 2 opportunities GANHO dentro do período


async def test_metas_de_outro_tenant_nao_aparecem(cenario):
    async with AsyncSessionLocal() as db:
        await create_or_update_meta(
            MetaCreate(periodo=PERIODO, tipo="RECEITA", valor_meta=Decimal("999")),
            current_user=_CurrentUser(cenario["tenant"], cenario["gestor"]), db=db,
        )
    async with AsyncSessionLocal() as db:
        metas_outro = await list_metas(periodo=PERIODO, current_user=_CurrentUser(cenario["outro_tenant"]), db=db)
    assert metas_outro == []


async def test_tipo_invalido_rejeitado(cenario):
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc_info:
            await create_or_update_meta(
                MetaCreate(periodo=PERIODO, tipo="INVALIDO", valor_meta=Decimal("100")),
                current_user=_CurrentUser(cenario["tenant"], cenario["gestor"]), db=db,
            )
    assert exc_info.value.status_code == 422


async def test_delete_remove_meta(cenario):
    async with AsyncSessionLocal() as db:
        criada = await create_or_update_meta(
            MetaCreate(periodo=PERIODO, tipo="RECEITA", valor_meta=Decimal("1000")),
            current_user=_CurrentUser(cenario["tenant"], cenario["gestor"]), db=db,
        )
    async with AsyncSessionLocal() as db:
        await delete_meta(criada["id"], current_user=_CurrentUser(cenario["tenant"]), db=db)
    async with AsyncSessionLocal() as db:
        metas = await list_metas(periodo=PERIODO, current_user=_CurrentUser(cenario["tenant"]), db=db)
    assert metas == []
