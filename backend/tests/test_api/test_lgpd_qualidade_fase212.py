"""Fase 212 (2ª proposta de evolução da Fase 209) — painel de qualidade de
dado LGPD-aware: GET /system/analytics/lgpd-qualidade sinaliza 3 lacunas de
conformidade por cliente (sem consentimento e ativo, consentimento sem
data, sem CPF/CNPJ). Postgres real: confirma contagens, score e isolamento
cross-tenant."""
import uuid

import pytest

from app.api.v1.system import analytics_lgpd_qualidade
from app.db.base import AsyncSessionLocal
from app.models.client import Client
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.anyio


class _CurrentUser:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


@pytest.fixture
async def cenario():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 212 LGPD", slug=f"teste-212-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        adv = User(
            email=f"adv-212-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Advogado Teste 212", role="ADVOGADO", tenant_id=tenant.id,
        )
        sem_consentimento = Client(
            tipo="PF", nome_completo="Sem Consentimento 212", status="ATIVO",
            lgpd_consent=False, cpf="111", tenant_id=tenant.id,
        )
        sem_cpf = Client(
            tipo="PF", nome_completo="Sem CPF 212", status="PROSPECTO",
            lgpd_consent=True, tenant_id=tenant.id,
        )
        completo = Client(
            tipo="PJ", nome_completo="Completo 212", status="ATIVO",
            lgpd_consent=True, cnpj="222", tenant_id=tenant.id,
        )
        db.add_all([adv, sem_consentimento, sem_cpf, completo])
        await db.commit()
        ids = {"tenant": tenant.id, "adv": adv.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(Client.__table__.delete().where(Client.tenant_id == ids["tenant"]))
        await db.execute(User.__table__.delete().where(User.id == ids["adv"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == ids["tenant"]))
        await db.commit()


async def test_lacunas_contadas_corretamente(cenario):
    async with AsyncSessionLocal() as db:
        resp = await analytics_lgpd_qualidade(current_user=_CurrentUser(cenario["tenant"]), db=db)
    assert resp["total_clientes"] == 3
    assert resp["lacunas"]["sem_consentimento_ativo"]["total"] == 1
    assert resp["lacunas"]["sem_documento_identificacao"]["total"] == 1
    assert resp["score_conformidade"] < 100


async def test_tenant_sem_clientes_score_cheio():
    async with AsyncSessionLocal() as db:
        resp = await analytics_lgpd_qualidade(current_user=_CurrentUser(uuid.uuid4()), db=db)
    assert resp["total_clientes"] == 0
    assert resp["score_conformidade"] == 100
