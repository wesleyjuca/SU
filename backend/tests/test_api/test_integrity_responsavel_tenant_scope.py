"""Fase 204 (achado MÉDIO da Fase 203) — `IntegrityRisk.responsavel_id` era
gravado sem checar o tenant do usuário referenciado, ao contrário de todo
outro FK do sistema (client_id/process_id sempre passam por um validador).
`GET /integrity/risks` fazia um outer join sem filtro de tenant no lado de
`User` — um ADMIN podia setar `responsavel_id` pra um UUID de usuário de
OUTRO escritório e ler de volta o `full_name` desse usuário.

Postgres real (não mock) — cria 2 tenants + 1 usuário em cada, reproduz o
ataque (setar responsavel_id pro usuário do outro tenant) e confirma que o
fix bloqueia com 422 em vez de aceitar."""
import uuid

import pytest
from fastapi import HTTPException

from app.api.v1.integrity import RiskCreate, RiskUpdate, create_risk, update_risk, list_risks
from app.db.base import AsyncSessionLocal
from app.models.integrity import IntegrityRisk
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _criar_tenant_e_usuario(db, sufixo: str):
    tenant = Tenant(name=f"Escritório teste {sufixo}", slug=f"teste-204-{sufixo}-{uuid.uuid4().hex[:8]}")
    db.add(tenant)
    await db.flush()
    user = User(
        email=f"user-204-{sufixo}-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x", full_name=f"Usuário {sufixo}", role="ADVOGADO",
        tenant_id=tenant.id,
    )
    db.add(user)
    await db.flush()
    return tenant, user


@pytest.fixture
async def cenario_dois_tenants():
    async with AsyncSessionLocal() as db:
        tenant_a, user_a = await _criar_tenant_e_usuario(db, "a")
        tenant_b, user_b = await _criar_tenant_e_usuario(db, "b")
        admin_a = User(
            email=f"admin-204-a-{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="x", full_name="Admin A", role="ADMIN", tenant_id=tenant_a.id,
        )
        db.add(admin_a)
        await db.flush()
        await db.commit()
        ids = {
            "tenant_a": tenant_a.id, "tenant_b": tenant_b.id,
            "user_a": user_a.id, "user_b": user_b.id, "admin_a": admin_a.id,
        }
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(IntegrityRisk.__table__.delete().where(
            IntegrityRisk.tenant_id.in_([ids["tenant_a"], ids["tenant_b"]])
        ))
        await db.execute(User.__table__.delete().where(
            User.id.in_([ids["user_a"], ids["user_b"], ids["admin_a"]])
        ))
        await db.execute(Tenant.__table__.delete().where(
            Tenant.id.in_([ids["tenant_a"], ids["tenant_b"]])
        ))
        await db.commit()


class _CurrentUser:
    def __init__(self, user_id, tenant_id):
        self.id = user_id
        self.tenant_id = tenant_id


async def test_create_risk_rejeita_responsavel_de_outro_tenant(cenario_dois_tenants):
    ids = cenario_dois_tenants
    admin_a = _CurrentUser(ids["admin_a"], ids["tenant_a"])
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await create_risk(
                RiskCreate(
                    risco="risco de teste", categoria="ETICA", probabilidade="MEDIA",
                    impacto="ALTO", controles="controles de teste",
                    responsavel_id=str(ids["user_b"]),  # usuário de OUTRO tenant
                ),
                current_user=admin_a, db=db,
            )
        assert exc.value.status_code == 422


async def test_create_risk_aceita_responsavel_do_mesmo_tenant(cenario_dois_tenants):
    ids = cenario_dois_tenants
    admin_a = _CurrentUser(ids["admin_a"], ids["tenant_a"])
    async with AsyncSessionLocal() as db:
        resultado = await create_risk(
            RiskCreate(
                risco="risco de teste", categoria="ETICA", probabilidade="MEDIA",
                impacto="ALTO", controles="controles de teste",
                responsavel_id=str(ids["user_a"]),  # usuário do MESMO tenant
            ),
            current_user=admin_a, db=db,
        )
        await db.commit()
    assert resultado["responsavel_id"] == str(ids["user_a"])


async def test_update_risk_rejeita_responsavel_de_outro_tenant(cenario_dois_tenants):
    ids = cenario_dois_tenants
    admin_a = _CurrentUser(ids["admin_a"], ids["tenant_a"])
    async with AsyncSessionLocal() as db:
        risk = IntegrityRisk(
            tenant_id=ids["tenant_a"], risco="r", categoria="ETICA", probabilidade="BAIXA",
            impacto="BAIXO", controles="c", created_by=ids["admin_a"],
        )
        db.add(risk)
        await db.flush()
        risk_id = str(risk.id)
        await db.commit()

    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await update_risk(
                risk_id, RiskUpdate(responsavel_id=str(ids["user_b"])),
                current_user=admin_a, db=db,
            )
        assert exc.value.status_code == 422


async def test_list_risks_nao_vaza_nome_de_usuario_de_outro_tenant(cenario_dois_tenants):
    """Mesmo que uma linha antiga (pré-fix) tenha um responsavel_id de outro
    tenant, o outer join com filtro de tenant não deve devolver o nome."""
    ids = cenario_dois_tenants
    admin_a = _CurrentUser(ids["admin_a"], ids["tenant_a"])
    async with AsyncSessionLocal() as db:
        # Insere direto no banco (bypassando o validador) pra simular uma
        # linha legada — confirma que list_risks() também está protegido,
        # não só os endpoints de escrita.
        risk = IntegrityRisk(
            tenant_id=ids["tenant_a"], risco="risco legado", categoria="ETICA",
            probabilidade="BAIXA", impacto="BAIXO", controles="c",
            responsavel_id=ids["user_b"], created_by=ids["admin_a"],
        )
        db.add(risk)
        await db.flush()
        await db.commit()

    async with AsyncSessionLocal() as db:
        riscos = await list_risks(current_user=admin_a, db=db)

    achado = next(r for r in riscos if r["risco"] == "risco legado")
    assert achado["responsavel_nome"] is None, "nome de usuário de outro tenant vazou via list_risks"
