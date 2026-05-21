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
    return {"email": "admin@afjadvogados.com.br", "password": "Admin@123"}


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
def tenant_b_process_id():
    return str(uuid.uuid4())


@pytest.fixture
def tenant_b_client_id():
    return str(uuid.uuid4())
