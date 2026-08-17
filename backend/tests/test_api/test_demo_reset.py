"""Fase 199 — o teste mais crítico do plano: prova que o reset do tenant
demo (a) nunca toca uma linha do tenant `afj`, (b) é idempotente, (c) o
endpoint manual é restrito a SUPERADMIN real (nem o ADMIN do próprio tenant
demo consegue disparar), (d) o login público continua funcionando logo após
o reset. Postgres real (AsyncSessionLocal), mesmo padrão de
test_hitl_flush_and_lock.py."""
import pytest
from sqlalchemy import func, select

from app.db.base import AsyncSessionLocal
from app.models.client import Client
from app.models.financial import FinancialEntry
from app.models.process import LegalProcess
from app.models.tenant import Tenant
from app.services.demo_fixtures import DEMO_ADMIN_EMAIL, DEMO_ADMIN_SENHA
from app.services.demo_reset import resetar_tenant_demo

pytestmark = pytest.mark.asyncio


async def _contagens(db, tenant_id) -> dict:
    return {
        "clients": (await db.execute(select(func.count()).select_from(Client).where(Client.tenant_id == tenant_id))).scalar(),
        "legal_processes": (await db.execute(select(func.count()).select_from(LegalProcess).where(LegalProcess.tenant_id == tenant_id))).scalar(),
        "financial_entries": (await db.execute(select(func.count()).select_from(FinancialEntry).where(FinancialEntry.tenant_id == tenant_id))).scalar(),
    }


async def _ids_afj_e_demo(db) -> tuple:
    afj = (await db.execute(select(Tenant.id).where(Tenant.slug == "afj"))).scalar_one_or_none()
    demo = (await db.execute(select(Tenant.id).where(Tenant.slug == "demo", Tenant.is_demo.is_(True)))).scalar_one_or_none()
    if afj is None or demo is None:
        pytest.skip("Seed (tenants afj/demo) não disponível neste ambiente")
    return afj, demo


async def test_reset_nao_toca_no_tenant_afj_e_e_idempotente():
    async with AsyncSessionLocal() as db:
        afj_id, demo_id = await _ids_afj_e_demo(db)
        afj_antes = await _contagens(db, afj_id)

        # Sujeira extra no tenant demo — simula uso real entre resets.
        db.add(Client(
            tipo="PF", nome_completo="Cliente Extra De Teste", tenant_id=demo_id,
            status="ATIVO", lgpd_consent=True,
        ))
        await db.commit()
        demo_antes = await _contagens(db, demo_id)
        assert demo_antes["clients"] >= 1

    async with AsyncSessionLocal() as db:
        resultado1 = await resetar_tenant_demo(db)

    async with AsyncSessionLocal() as db:
        afj_depois = await _contagens(db, afj_id)
        demo_depois = await _contagens(db, demo_id)

    assert afj_depois == afj_antes, (
        f"reset do tenant demo alterou o tenant afj — antes={afj_antes} depois={afj_depois}"
    )
    # Volta pro conjunto fictício original do seed (5 clientes/5 processos/5 lançamentos).
    assert demo_depois == {"clients": 5, "legal_processes": 5, "financial_entries": 5}
    assert isinstance(resultado1["apagados"], dict)

    # Idempotência: rodar de novo não duplica nem lança exceção.
    async with AsyncSessionLocal() as db:
        resultado2 = await resetar_tenant_demo(db)
        demo_depois2 = await _contagens(db, demo_id)
    assert demo_depois2 == demo_depois
    assert resultado2["tenant_id"] == resultado1["tenant_id"]


async def test_reset_manual_restrito_a_superadmin_real(client, auth_headers, superadmin_headers):
    # ADMIN comum (tenant afj) não pode disparar o reset do tenant demo.
    resp = await client.post("/api/v1/tenants/demo/reset", headers=auth_headers)
    assert resp.status_code == 403, resp.text

    # ADMIN do próprio tenant demo também não pode.
    login = await client.post("/api/v1/auth/login", json={"email": DEMO_ADMIN_EMAIL, "password": DEMO_ADMIN_SENHA})
    if login.status_code == 200:
        demo_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        resp2 = await client.post("/api/v1/tenants/demo/reset", headers=demo_headers)
        assert resp2.status_code == 403, resp2.text

    # SUPERADMIN real consegue.
    resp3 = await client.post("/api/v1/tenants/demo/reset", headers=superadmin_headers)
    assert resp3.status_code == 200, resp3.text
    assert "apagados" in resp3.json()

    # Login público continua funcionando logo após o reset (usuários recriados).
    login2 = await client.post("/api/v1/auth/login", json={"email": DEMO_ADMIN_EMAIL, "password": DEMO_ADMIN_SENHA})
    assert login2.status_code == 200, login2.text
