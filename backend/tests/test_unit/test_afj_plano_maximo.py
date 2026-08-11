"""Fase 170 — o escritório raiz da plataforma (slug="afj") deve sempre ter
plan="MAXIMO" e isento=True. Cobre: o tier existe e é ilimitado; criar ou
editar um tenant não pode atribuir "MAXIMO" a ninguém além do raiz nem
tirar o raiz do "MAXIMO"; a isenção de cobrança (_billing_summary) passou a
ler a coluna Tenant.isento em vez de comparar slug; e require_active_tenant
nunca bloqueia escrita de um tenant isento."""
import uuid

import pytest
from fastapi import HTTPException

from app.api.v1.tenants_admin import PLAN_TIERS, TenantCreate, TenantPatch, create_tenant, update_tenant
from app.api.v1.tenant import _billing_summary
from app.core.exceptions import ForbiddenError
from app.dependencies import require_active_tenant
from app.models.tenant import Tenant


class _FakeUser:
    def __init__(self, id="u1", tenant_id=None, role="SUPERADMIN"):
        self.id = id
        self.tenant_id = tenant_id
        self.role = role


class _FakeResult:
    def __init__(self, scalar=None):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class _FakeDB:
    """Fila de resultados consumidos em ordem — mesmo padrão de
    test_tenant_logo_fase143.py."""
    def __init__(self, *scalars):
        self._results = [_FakeResult(scalar=s) for s in scalars]
        self.added = []
        self.committed = False

    async def execute(self, query):
        return self._results.pop(0) if self._results else _FakeResult()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def flush(self):
        pass


def _tenant(slug="outro-escritorio", plan="STANDARD", isento=False, id=None):
    return Tenant(id=id or uuid.uuid4(), name="X", slug=slug, plan=plan, isento=isento)


# ─── PLAN_TIERS ──────────────────────────────────────────────────────────

def test_maximo_tier_existe_e_e_ilimitado():
    assert PLAN_TIERS["MAXIMO"] == {"max_users": 0, "max_storage_gb": 0}


# ─── criação de tenant não pode usar MAXIMO ────────────────────────────────

async def test_create_tenant_rejeita_plano_maximo():
    db = _FakeDB(None)  # select(User.id) por e-mail duplicado → nenhum
    body = TenantCreate(name="Novo Escritório", plan="MAXIMO", admin_email="a@b.com", admin_name="A")
    with pytest.raises(HTTPException) as exc:
        await create_tenant(body, current_user=_FakeUser(), db=db)
    assert exc.value.status_code == 422
    assert "exclusivo" in exc.value.detail.lower()


async def test_create_tenant_rejeita_plano_maximo_caixa_variada():
    db = _FakeDB(None)
    body = TenantCreate(name="Novo Escritório", plan="maximo", admin_email="a@b.com", admin_name="A")
    with pytest.raises(HTTPException) as exc:
        await create_tenant(body, current_user=_FakeUser(), db=db)
    assert exc.value.status_code == 422


# ─── PATCH não pode tirar o raiz do MAXIMO nem dar MAXIMO pra outro ────────

async def test_update_tenant_raiz_nao_pode_trocar_de_plano():
    tenant = _tenant(slug="afj", plan="MAXIMO", isento=True)
    db = _FakeDB(tenant)
    with pytest.raises(HTTPException) as exc:
        await update_tenant(str(tenant.id), TenantPatch(plan="ENTERPRISE"), current_user=_FakeUser(), db=db)
    assert exc.value.status_code == 422
    assert "sempre usa o plano" in exc.value.detail.lower()


async def test_update_tenant_comum_nao_pode_virar_maximo():
    tenant = _tenant(slug="cliente-x", plan="STANDARD")
    db = _FakeDB(tenant)
    with pytest.raises(HTTPException) as exc:
        await update_tenant(str(tenant.id), TenantPatch(plan="MAXIMO"), current_user=_FakeUser(), db=db)
    assert exc.value.status_code == 422
    assert "exclusivo" in exc.value.detail.lower()


async def test_update_tenant_raiz_pode_reafirmar_maximo():
    tenant = _tenant(slug="afj", plan="MAXIMO", isento=True)
    db = _FakeDB(tenant)
    out = await update_tenant(str(tenant.id), TenantPatch(plan="MAXIMO"), current_user=_FakeUser(), db=db)
    assert out["plan"] == "MAXIMO"
    assert db.committed is True


async def test_update_tenant_comum_pode_trocar_entre_planos_normais():
    tenant = _tenant(slug="cliente-x", plan="STANDARD")
    db = _FakeDB(tenant)
    out = await update_tenant(str(tenant.id), TenantPatch(plan="PRO"), current_user=_FakeUser(), db=db)
    assert out["plan"] == "PRO"


# ─── _billing_summary generalizado (coluna isento, não mais slug) ─────────

async def test_billing_summary_isento_por_coluna_independente_do_slug():
    tenant = _tenant(slug="qualquer-slug", plan="PRO", isento=True)
    out = await _billing_summary(_FakeDB(), tenant)
    assert out["status"] == "ISENTO"


async def test_billing_summary_tenant_comum_sem_billing_account():
    tenant = _tenant(slug="cliente-y", plan="STANDARD", isento=False)
    out = await _billing_summary(_FakeDB(None), tenant)
    assert out["status"] == "NAO_CONFIGURADO"


# ─── require_active_tenant nunca bloqueia tenant isento ────────────────────

class _FakeRequest:
    def __init__(self, method="POST"):
        self.method = method


async def test_require_active_tenant_nao_bloqueia_isento_mesmo_com_billing_suspenso():
    tenant_id = uuid.uuid4()
    user = _FakeUser(tenant_id=tenant_id, role="ADVOGADO")
    # 1a query (Tenant.isento) → True: nunca deveria nem consultar BillingAccount.
    db = _FakeDB(True)
    result_user = await require_active_tenant(_FakeRequest("POST"), current_user=user, db=db)
    assert result_user is user


async def test_require_active_tenant_bloqueia_tenant_comum_suspenso():
    tenant_id = uuid.uuid4()
    user = _FakeUser(tenant_id=tenant_id, role="ADVOGADO")
    # 1a query (Tenant.isento) → False/None; 2a query (BillingAccount.status) → SUSPENSO.
    db = _FakeDB(False, "SUSPENSO")
    with pytest.raises(ForbiddenError):
        await require_active_tenant(_FakeRequest("POST"), current_user=user, db=db)
