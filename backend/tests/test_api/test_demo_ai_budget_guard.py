"""Fase 199 — achado do Plan agent (não estava no levantamento original):
`PUT /system/ai-budgets` deixava qualquer ADMIN/SÓCIO editar/remover o teto
de IA de qualquer usuário do PRÓPRIO tenant, sem excluir a si mesmo. Sem um
guard aqui, o ADMIN do tenant demo poderia remover o teto seedado da própria
conta e escapar do controle de custo — o único guard dos 4 desta fase que
protege contra o próprio usuário demo, não contra I/O externo."""
import pytest

from app.services.demo_fixtures import DEMO_ADMIN_EMAIL, DEMO_ADMIN_SENHA

pytestmark = pytest.mark.asyncio


async def test_admin_demo_nao_consegue_alterar_o_proprio_teto_de_ia(client):
    login = await client.post("/api/v1/auth/login", json={"email": DEMO_ADMIN_EMAIL, "password": DEMO_ADMIN_SENHA})
    if login.status_code != 200:
        pytest.skip("Login do tenant demo falhou — seed data não disponível")
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    demo_user_id = login.json()["user"]["id"]

    resp = await client.put(
        "/api/v1/system/ai-budgets",
        json={"user_id": demo_user_id, "monthly_limit_usd": 9999.0, "alert_pct": 80},
        headers=headers,
    )
    assert resp.status_code == 403, resp.text
    assert "demonstração" in resp.json()["detail"].lower()

    # Também não deve conseguir REMOVER o teto (monthly_limit_usd nulo).
    resp2 = await client.put(
        "/api/v1/system/ai-budgets",
        json={"user_id": demo_user_id, "monthly_limit_usd": None, "alert_pct": 80},
        headers=headers,
    )
    assert resp2.status_code == 403, resp2.text
