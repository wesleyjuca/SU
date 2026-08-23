import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def test_user():
    # Fase 228 — achado da Fase 222: este e-mail (".com.br") não batia com
    # nenhum dos 2 usuários ADMIN reais do seed (admin@afj.com.br,
    # admin@afjadvogados.com, sem ".br") — todo teste dependente de
    # `auth_headers` pulava silenciosamente com "Login failed" neste
    # ambiente, independente da fase, desde pelo menos a Fase 222.
    return {"email": "admin@afj.com.br", "password": "Admin@123"}


@pytest.fixture
async def auth_headers(client, test_user):
    res = await client.post("/api/v1/auth/login", json=test_user)
    if res.status_code != 200:
        pytest.skip("Login failed — seed data not available")
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tenant_a_headers(auth_headers):
    return auth_headers


@pytest.fixture
async def superadmin_headers(client):
    """Fase 180 — endpoints de exclusão permanente exigem SUPERADMIN, um papel
    que `test_user`/`auth_headers` (ADMIN) não cobre. Mesmo espírito de
    `auth_headers`: pula (não falha) se o seed de SUPERADMIN não estiver
    disponível no ambiente rodando os testes."""
    res = await client.post("/api/v1/auth/login", json={"email": "super@afj.com.br", "password": "Super@123"})
    if res.status_code != 200:
        pytest.skip("Login SUPERADMIN falhou — seed data não disponível")
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def demo_headers(client):
    """Fase 199 — login com a credencial pública do tenant de demonstração.
    Mesmo espírito de `superadmin_headers`: pula (não falha) se o seed do
    tenant demo não estiver disponível no ambiente rodando os testes."""
    from app.services.demo_fixtures import DEMO_ADMIN_EMAIL, DEMO_ADMIN_SENHA

    res = await client.post("/api/v1/auth/login", json={"email": DEMO_ADMIN_EMAIL, "password": DEMO_ADMIN_SENHA})
    if res.status_code != 200:
        pytest.skip("Login do tenant demo falhou — seed data não disponível")
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tenant_b_process_id():
    return str(uuid.uuid4())


@pytest.fixture
def tenant_b_client_id():
    return str(uuid.uuid4())
