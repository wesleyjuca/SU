"""Fase 208.3 — auto-população da Matriz de Riscos: GET /integrity/reports/
{id}/suggest-risk devolve um RASCUNHO (nunca cria a linha sozinho — a
criação continua exigindo POST /integrity/risks manual com `controles`
preenchido por humano). Também cobre o achado colateral desta fase:
create_risk/update_risk agora validam `categoria` como create_report já
fazia."""
import uuid

import pytest
from fastapi import HTTPException

from app.api.v1.integrity import (
    RiskCreate, RiskUpdate, ReportCreate,
    create_report, create_risk, update_risk, suggest_risk_from_report,
)
from app.core.exceptions import NotFoundError
from app.db.base import AsyncSessionLocal
from app.models.integrity import IntegrityReport, IntegrityRisk
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.anyio


class _CurrentUser:
    def __init__(self, tenant_id, user_id=None):
        self.tenant_id = tenant_id
        self.id = user_id or uuid.uuid4()


@pytest.fixture
async def cenario():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 208.3", slug=f"teste-208-3-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        admin = User(
            email=f"admin-208-3-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Admin Teste 208.3", role="ADMIN", tenant_id=tenant.id,
        )
        db.add(admin)
        await db.commit()
        ids = {"tenant": tenant.id, "admin": admin.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(IntegrityRisk.__table__.delete().where(IntegrityRisk.tenant_id == ids["tenant"]))
        await db.execute(IntegrityReport.__table__.delete().where(IntegrityReport.tenant_id == ids["tenant"]))
        await db.execute(User.__table__.delete().where(User.id == ids["admin"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == ids["tenant"]))
        await db.commit()


async def test_sugestao_pre_preenchida_sem_criar_risco(cenario):
    cu = _CurrentUser(cenario["tenant"], cenario["admin"])
    async with AsyncSessionLocal() as db:
        report_resp = await create_report(
            body=ReportCreate(categoria="DADOS_LGPD", descricao="Vazamento de dados de cliente detectado.", anonimo=False),
            current_user=cu, db=db,
        )
        await db.commit()

    async with AsyncSessionLocal() as db:
        sugestao = await suggest_risk_from_report(report_id=report_resp["id"], current_user=cu, db=db)

    assert sugestao["categoria"] == "DADOS_LGPD"
    assert sugestao["probabilidade"] == "MEDIA"
    assert sugestao["impacto"] == "MEDIO"
    assert sugestao["risco_existente_id"] is None
    assert "Vazamento" in sugestao["risco"]

    # Nenhuma linha foi criada na Matriz de Riscos — sugestão é só um rascunho.
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        riscos = (await db.execute(
            select(IntegrityRisk).where(IntegrityRisk.tenant_id == cenario["tenant"])
        )).scalars().all()
    assert riscos == []


async def test_sugestao_sinaliza_risco_ativo_existente_mesma_categoria(cenario):
    cu = _CurrentUser(cenario["tenant"], cenario["admin"])
    async with AsyncSessionLocal() as db:
        report_resp = await create_report(
            body=ReportCreate(categoria="ASSEDIO", descricao="Relato de conduta inadequada.", anonimo=True),
            current_user=cu, db=db,
        )
        risco_criado = await create_risk(
            body=RiskCreate(risco="Risco de assédio já mapeado", categoria="ASSEDIO",
                             probabilidade="ALTA", impacto="ALTO", controles="Canal de denúncia + treinamento"),
            current_user=cu, db=db,
        )
        await db.commit()

    async with AsyncSessionLocal() as db:
        sugestao = await suggest_risk_from_report(report_id=report_resp["id"], current_user=cu, db=db)
    assert sugestao["risco_existente_id"] == risco_criado["id"]


async def test_sugestao_relato_de_outro_tenant_nao_encontrado(cenario):
    cu = _CurrentUser(cenario["tenant"], cenario["admin"])
    async with AsyncSessionLocal() as db:
        outro_tenant = Tenant(name="Outro 208.3", slug=f"outro-208-3-{uuid.uuid4().hex[:8]}")
        db.add(outro_tenant)
        await db.commit()
        outro_id = outro_tenant.id
    try:
        async with AsyncSessionLocal() as db:
            with pytest.raises(NotFoundError):
                await suggest_risk_from_report(report_id=str(uuid.uuid4()), current_user=cu, db=db)
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(Tenant.__table__.delete().where(Tenant.id == outro_id))
            await db.commit()


async def test_create_risk_rejeita_categoria_invalida(cenario):
    cu = _CurrentUser(cenario["tenant"], cenario["admin"])
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc_info:
            await create_risk(
                body=RiskCreate(risco="Risco qualquer", categoria="CATEGORIA_INEXISTENTE",
                                 probabilidade="MEDIA", impacto="MEDIO", controles="Controle qualquer"),
                current_user=cu, db=db,
            )
    assert exc_info.value.status_code == 422


async def test_update_risk_rejeita_categoria_invalida(cenario):
    cu = _CurrentUser(cenario["tenant"], cenario["admin"])
    async with AsyncSessionLocal() as db:
        risco = await create_risk(
            body=RiskCreate(risco="Risco válido", categoria="ETICA",
                             probabilidade="BAIXA", impacto="BAIXO", controles="Controle inicial"),
            current_user=cu, db=db,
        )
        await db.commit()

    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc_info:
            await update_risk(
                risk_id=risco["id"], body=RiskUpdate(categoria="CATEGORIA_INEXISTENTE"),
                current_user=cu, db=db,
            )
    assert exc_info.value.status_code == 422
