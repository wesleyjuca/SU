"""Fase 180.x — regressão: /integrations/hub/{provider}/oauth/callback não
pode exigir o JWT do sistema. Quem bate nessa rota é o navegador sendo
redirecionado pelo provedor (Google/Stripe/Mercado Pago) depois do usuário
autorizar — nunca carrega header Authorization. Achado ao testar a conexão
real do Google Workspace: o router inteiro (`integrations_hub.router`)
estava montado com `dependencies=_BLOCK_STAFF` em `api/v1/router.py`,
incluindo o próprio callback, que sempre respondia 401 antes de rodar
qualquer lógica — quebrando a conexão OAuth de todo provedor do hub."""
import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.anyio


async def test_oauth_callback_nao_exige_autenticacao(client: AsyncClient):
    """Sem nenhum header Authorization — exatamente como o redirect real do
    provedor chega. Não pode devolver 401; deve seguir a lógica própria do
    endpoint (redirect com erro pra state/code inválidos, nesse caso)."""
    res = await client.get(
        "/api/v1/integrations/hub/google_workspace/oauth/callback",
        params={"code": "fake-code", "state": "fake-state"},
        follow_redirects=False,
    )
    assert res.status_code != 401
    assert "Token de autenticação" not in res.text
    # state inválido (não assinado por nós) -> redirect de erro, não 401/500
    assert res.status_code in (302, 307)
    assert "hub_oauth=google_workspace_erro" in res.headers.get("location", "")
