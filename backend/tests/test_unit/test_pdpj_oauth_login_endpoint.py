"""Fase 177.1b — endpoint POST /integrations/hub/pdpj/oauth/login. Testa a
tradução de erro (401 do Keycloak → mensagem amigável, sem vazar detalhe cru)
e o caminho de sucesso, chamando a função do endpoint diretamente (sem
levantar app/TestClient — mesmo espírito enxuto dos outros testes de
integration_hub)."""
import httpx
import pytest
from fastapi import HTTPException

from app.api.v1 import integrations_hub as router_mod
from app.services import integration_hub as ih


class _FakeUser:
    def __init__(self):
        self.id = "user1"
        self.tenant_id = "t1"


class _FakeDB:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class _FakeHttpxResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def _http_status_error(status_code):
    return httpx.HTTPStatusError("boom", request=None, response=_FakeHttpxResponse(status_code))


def _limpar():
    from app.config import settings
    settings.PDPJ_OAUTH_CLIENT_ID = ""
    settings.PDPJ_OAUTH_CLIENT_SECRET = ""


@pytest.mark.asyncio
async def test_login_nao_configurado_devolve_422_orientando_alternativa(monkeypatch):
    _limpar()
    body = router_mod.PdpjLoginBody(username="u", password="p")
    with pytest.raises(HTTPException) as exc_info:
        await router_mod.hub_pdpj_oauth_login(body, current_user=_FakeUser(), db=_FakeDB())
    assert exc_info.value.status_code == 422
    assert "Colar token manualmente" in exc_info.value.detail


@pytest.mark.asyncio
async def test_login_credencial_invalida_401_vira_mensagem_amigavel(monkeypatch):
    from app.config import settings
    settings.PDPJ_OAUTH_CLIENT_ID = "cid"
    settings.PDPJ_OAUTH_CLIENT_SECRET = "csecret"

    async def _fake_exchange(provider, username, password):
        raise _http_status_error(401)
    monkeypatch.setattr(ih, "exchange_oauth_password", _fake_exchange)

    body = router_mod.PdpjLoginBody(username="usuario.cnj", password="senha-errada")
    with pytest.raises(HTTPException) as exc_info:
        await router_mod.hub_pdpj_oauth_login(body, current_user=_FakeUser(), db=_FakeDB())
    assert exc_info.value.status_code == 422
    assert "inválidos" in exc_info.value.detail
    # não deve vazar detalhe cru da resposta do Keycloak
    assert "boom" not in exc_info.value.detail
    _limpar()


@pytest.mark.asyncio
async def test_login_keycloak_fora_do_ar_5xx_vira_502(monkeypatch):
    from app.config import settings
    settings.PDPJ_OAUTH_CLIENT_ID = "cid"
    settings.PDPJ_OAUTH_CLIENT_SECRET = "csecret"

    async def _fake_exchange(provider, username, password):
        raise _http_status_error(503)
    monkeypatch.setattr(ih, "exchange_oauth_password", _fake_exchange)

    body = router_mod.PdpjLoginBody(username="usuario.cnj", password="senha")
    with pytest.raises(HTTPException) as exc_info:
        await router_mod.hub_pdpj_oauth_login(body, current_user=_FakeUser(), db=_FakeDB())
    assert exc_info.value.status_code == 502
    _limpar()


@pytest.mark.asyncio
async def test_login_sucesso_salva_tokens_e_comita(monkeypatch):
    from app.config import settings
    settings.PDPJ_OAUTH_CLIENT_ID = "cid"
    settings.PDPJ_OAUTH_CLIENT_SECRET = "csecret"

    async def _fake_exchange(provider, username, password):
        assert provider == "pdpj"
        assert username == "usuario.cnj"
        assert password == "senha-certa"
        return {"access_token": "tok_novo", "refresh_token": "ref_novo", "expires_in": 300}
    monkeypatch.setattr(ih, "exchange_oauth_password", _fake_exchange)

    salvo = {}

    async def _fake_save(db, tenant_id, provider, tokens, connected_by=None):
        salvo["tenant_id"] = tenant_id
        salvo["provider"] = provider
        salvo["tokens"] = tokens
        salvo["connected_by"] = connected_by
        return object()
    monkeypatch.setattr(ih, "save_oauth_tokens", _fake_save)

    db = _FakeDB()
    body = router_mod.PdpjLoginBody(username="usuario.cnj", password="senha-certa")
    result = await router_mod.hub_pdpj_oauth_login(body, current_user=_FakeUser(), db=db)

    assert result["status"] == "CONECTADA"
    assert salvo["provider"] == "pdpj"
    assert salvo["tenant_id"] == "t1"
    assert salvo["connected_by"] == "user1"
    assert db.commits == 1
    _limpar()
