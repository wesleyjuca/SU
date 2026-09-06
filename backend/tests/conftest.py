import os

# ATENÇÃO À ORDEM: isto precisa rodar ANTES de `from app.main import app`, que
# importa `app.db.base` e cria o engine. Ver a nota em `app/db/base.py` — sem
# NullPool, uma conexão criada no loop de um teste é reusada no loop do teste
# seguinte e o teardown estoura `RuntimeError: Event loop is closed`.
os.environ.setdefault("AFJ_DB_NULLPOOL", "1")

import pytest  # noqa: E402
import uuid  # noqa: E402
from httpx import AsyncClient, ASGITransport  # noqa: E402
from app.main import app  # noqa: E402


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


# Cache de token por processo de teste. Antes, `auth_headers` era por teste e
# a suíte fazia ~180 logins — contra um teto de 10/min por IP
# (`RATE_LIMIT_RULES["auth"]`). Com Redis disponível, a suíte se autobloqueava:
# a partir do 11º teste todo login voltava 429 e `auth_headers` pulava, gerando
# dezenas de "Login failed — seed data not available" que parecem falta de seed
# e não são. (No CI isso não aparecia porque lá não há Redis e o rate limit vira
# no-op — a divergência entre os dois ambientes escondia o problema nos dois.)
_TOKEN_CACHE: dict[str, str] = {}


async def _obter_token(client, email: str, senha: str) -> str | None:
    """Loga uma vez por processo e reusa o access token. Devolve None se o
    login falhar por motivo real (seed ausente/credencial errada)."""
    if email in _TOKEN_CACHE:
        return _TOKEN_CACHE[email]
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": senha})
    if res.status_code != 200:
        return None
    token = res.json()["access_token"]
    _TOKEN_CACHE[email] = token
    return token


@pytest.fixture
async def auth_headers(client, test_user):
    token = await _obter_token(client, test_user["email"], test_user["password"])
    if token is None:
        pytest.skip("Login failed — seed data not available")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def auth_headers_descartavel(client, test_user):
    """Token novo, FORA do cache — para testes que destroem o próprio token.

    `test_logout_invalidates_token` põe o token na blacklist de propósito. Se
    ele usar o token compartilhado, todo teste seguinte recebe 401 e a suíte
    inteira vira falha em cascata (observado ao vivo). Um teste que destrói um
    recurso precisa destruir o dele, não o de todo mundo."""
    res = await client.post("/api/v1/auth/login", json=test_user)
    if res.status_code != 200:
        pytest.skip("Login failed — seed data not available")
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def tenant_a_headers(auth_headers):
    return auth_headers


@pytest.fixture
async def superadmin_headers(client):
    """Fase 180 — endpoints de exclusão permanente exigem SUPERADMIN, um papel
    que `test_user`/`auth_headers` (ADMIN) não cobre. Mesmo espírito de
    `auth_headers`: pula (não falha) se o seed de SUPERADMIN não estiver
    disponível no ambiente rodando os testes."""
    token = await _obter_token(client, "super@afj.com.br", "Super@123")
    if token is None:
        pytest.skip("Login SUPERADMIN falhou — seed data não disponível")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def demo_headers(client):
    """Fase 199 — login com a credencial pública do tenant de demonstração.
    Mesmo espírito de `superadmin_headers`: pula (não falha) se o seed do
    tenant demo não estiver disponível no ambiente rodando os testes."""
    from app.services.demo_fixtures import DEMO_ADMIN_EMAIL, DEMO_ADMIN_SENHA

    token = await _obter_token(client, DEMO_ADMIN_EMAIL, DEMO_ADMIN_SENHA)
    if token is None:
        pytest.skip("Login do tenant demo falhou — seed data não disponível")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tenant_b_process_id():
    return str(uuid.uuid4())


@pytest.fixture
def tenant_b_client_id():
    return str(uuid.uuid4())
