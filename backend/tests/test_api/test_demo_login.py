"""Login sem senha no tenant público de demonstração — POST /auth/demo-login
não recebe nenhuma credencial, resolve o único destino possível (ADMIN do
tenant slug=="demo" AND is_demo=True) internamente. Prova: (a) token emitido
funciona num endpoint autenticado de verdade e pertence ao tenant demo,
(b) rate-limit de anti-abuso dispara, (c) o tenant `afj` nunca é tocado."""
import pytest
from sqlalchemy import func, select

from app.db.base import AsyncSessionLocal
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _limpar_rate_limit_demo_login():
    # O contador de anti-abuso é por IP (app/api/v1/auth.py); o cliente de
    # teste (ASGITransport) sempre reporta o mesmo IP fixo, então todos os
    # testes deste arquivo compartilham a mesma chave Redis — sem isso, um
    # teste que estoura o teto deixaria os seguintes sempre em 429.
    from app.db.redis import get_redis
    redis = await get_redis()
    if redis:
        try:
            keys = [k async for k in redis.scan_iter(match="demo_login:*")]
            if keys:
                await redis.delete(*keys)
        except Exception:
            pass
    yield


async def _demo_tenant_id(db):
    tenant_id = (await db.execute(
        select(Tenant.id).where(Tenant.slug == "demo", Tenant.is_demo.is_(True))
    )).scalar_one_or_none()
    if tenant_id is None:
        pytest.skip("Seed do tenant demo não disponível neste ambiente")
    return tenant_id


async def test_demo_login_sem_corpo_emite_token_valido(client):
    resp = await client.post("/api/v1/auth/demo-login")
    if resp.status_code == 503:
        pytest.skip("Seed do tenant demo não disponível neste ambiente")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["user"]["role"] == "ADMIN"

    async with AsyncSessionLocal() as db:
        demo_id = await _demo_tenant_id(db)
        user = (await db.execute(select(User).where(User.id == data["user"]["id"]))).scalar_one()
        assert str(user.tenant_id) == str(demo_id)

    # Token emitido funciona de verdade num endpoint autenticado.
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    processes_resp = await client.get("/api/v1/processes", headers=headers)
    assert processes_resp.status_code == 200, processes_resp.text


async def test_demo_login_nao_altera_tenant_afj(client):
    async with AsyncSessionLocal() as db:
        afj_id = (await db.execute(select(Tenant.id).where(Tenant.slug == "afj"))).scalar_one_or_none()
        if afj_id is None:
            pytest.skip("Seed do tenant afj não disponível neste ambiente")
        users_antes = (await db.execute(
            select(func.count()).select_from(User).where(User.tenant_id == afj_id)
        )).scalar()

    resp = await client.post("/api/v1/auth/demo-login")
    if resp.status_code == 503:
        pytest.skip("Seed do tenant demo não disponível neste ambiente")
    assert resp.status_code == 200, resp.text

    async with AsyncSessionLocal() as db:
        users_depois = (await db.execute(
            select(func.count()).select_from(User).where(User.tenant_id == afj_id)
        )).scalar()
    assert users_depois == users_antes


async def test_demo_login_rate_limit_anti_abuso(client):
    last_status = None
    for _ in range(25):
        resp = await client.post("/api/v1/auth/demo-login")
        last_status = resp.status_code
        if resp.status_code == 503:
            pytest.skip("Seed do tenant demo não disponível neste ambiente")
        if resp.status_code == 429:
            break
    assert last_status == 429, "esperava 429 após estourar o teto de anti-abuso do demo-login"
