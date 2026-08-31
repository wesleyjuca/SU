"""Fase 256 — reformulação da área de Configurações. Teste de regressão
pros 2 bugs reais confirmados e corrigidos nesta fase (Postgres+Redis
reais, mesmo padrão direto-por-função já usado nesta sessão):

1. `GET /tenant/theme`/`GET /tenant/config` sempre devolviam
   `office_name`/`slogan` como `None`, mesmo já salvos via `PUT
   /tenant/branding` — causa-raiz em `core/tenant.py::get_tenant_config()`,
   que nunca incluía `TenantConfig.extra_data` no dict cacheado (embora
   `get_theme()` já esperasse essa chave sob `"metadata"`).
2. `PUT /tenant/branding` com `dashboard_widgets` sempre devolvia 200 OK
   sem persistir nada — `BrandingUpdate` não tinha esse campo, Pydantic
   descartava silenciosamente.
"""
import uuid

import pytest

from app.api.v1.tenant import BrandingUpdate, get_config, get_theme, update_branding
from app.core.tenant import invalidate_tenant_cache
from app.db.base import AsyncSessionLocal
from app.models.tenant import Tenant

pytestmark = pytest.mark.anyio


class _CurrentUser:
    def __init__(self, tenant_id, uid=None):
        self.tenant_id = tenant_id
        self.id = uid or uuid.uuid4()


@pytest.fixture
async def tenant_id():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 256", slug=f"teste-256-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.commit()
        tid = tenant.id
    yield tid
    async with AsyncSessionLocal() as db:
        await db.execute(Tenant.__table__.delete().where(Tenant.id == tid))
        await db.commit()


async def test_office_name_e_slogan_voltam_no_get_apos_salvar(tenant_id):
    cu = _CurrentUser(tenant_id)

    async with AsyncSessionLocal() as db:
        resp_put = await update_branding(
            BrandingUpdate(office_name="Escritório Teste 256", slogan="Slogan de teste"),
            current_user=cu, db=db,
        )
        await db.commit()
    # O PUT em si sempre respondeu certo (lê direto do ORM, não do cache)
    # — o bug era só nas leituras GET seguintes.
    assert resp_put.office_name == "Escritório Teste 256"
    assert resp_put.slogan == "Slogan de teste"

    async with AsyncSessionLocal() as db:
        resp_theme = await get_theme(current_user=cu, db=db)
    assert resp_theme.office_name == "Escritório Teste 256", (
        "GET /tenant/theme deveria refletir office_name já salvo, não voltar None"
    )
    assert resp_theme.slogan == "Slogan de teste"

    async with AsyncSessionLocal() as db:
        resp_config = await get_config(current_user=cu, db=db)
    assert resp_config.office_name == "Escritório Teste 256"
    assert resp_config.slogan == "Slogan de teste"

    await invalidate_tenant_cache(f"teste-256-{str(tenant_id)[:8]}")  # limpeza best-effort


async def test_dashboard_widgets_persiste_apos_salvar(tenant_id):
    cu = _CurrentUser(tenant_id)

    async with AsyncSessionLocal() as db:
        await update_branding(
            BrandingUpdate(dashboard_widgets=["processos_ativos", "custo_ia_mes"]),
            current_user=cu, db=db,
        )
        await db.commit()

    async with AsyncSessionLocal() as db:
        resp_config = await get_config(current_user=cu, db=db)
    assert resp_config.dashboard_widgets == ["processos_ativos", "custo_ia_mes"], (
        "PUT /tenant/branding com dashboard_widgets deveria persistir — antes era descartado "
        "silenciosamente porque BrandingUpdate não tinha esse campo"
    )
