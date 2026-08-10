"""Fase 165 — `enviar_whatsapp()` passa a registrar last_success_at/last_error_at
na `TenantIntegration` a cada envio real, não só no teste manual de conexão."""
import asyncio
import sys
import types


def setup_module(module):
    if "cryptography" in sys.modules:
        return
    fake_crypto = types.ModuleType("cryptography")
    fake_fernet_mod = types.ModuleType("cryptography.fernet")

    class InvalidToken(Exception):
        pass

    class Fernet:
        def __init__(self, key):
            self.key = key

        @staticmethod
        def generate_key():
            return b"0" * 32

        def encrypt(self, data):
            return b"ENC:" + data

        def decrypt(self, token):
            if not token.startswith(b"ENC:"):
                raise InvalidToken()
            return token[4:]

    fake_fernet_mod.Fernet = Fernet
    fake_fernet_mod.InvalidToken = InvalidToken
    fake_crypto.fernet = fake_fernet_mod
    sys.modules["cryptography"] = fake_crypto
    sys.modules["cryptography.fernet"] = fake_fernet_mod


class _FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class _FakeAsyncClient:
    responses = []

    def __init__(self, timeout=None):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        return _FakeAsyncClient.responses.pop(0)


def test_envio_com_sucesso_via_template_registra_sucesso(monkeypatch):
    from app.services import whatsapp

    chamadas = []

    async def _fake_get_credentials(db, tenant_id, provider):
        return {"phone_number_id": "123", "access_token": "tok"}

    async def _fake_registrar_uso(db, tenant_id, provider, sucesso, detalhe=None):
        chamadas.append({"sucesso": sucesso, "detalhe": detalhe})

    monkeypatch.setattr(whatsapp.integration_hub, "get_credentials", _fake_get_credentials)
    monkeypatch.setattr(whatsapp.integration_hub, "registrar_uso", _fake_registrar_uso)
    _FakeAsyncClient.responses = [_FakeResponse(200)]
    original = whatsapp.httpx.AsyncClient
    whatsapp.httpx.AsyncClient = _FakeAsyncClient
    try:
        ok = asyncio.run(whatsapp.enviar_whatsapp(None, "t1", "11999998888", "texto"))
    finally:
        whatsapp.httpx.AsyncClient = original

    assert ok is True
    assert chamadas == [{"sucesso": True, "detalhe": None}]


def test_envio_falha_nos_2_formatos_registra_falha_com_detalhe(monkeypatch):
    from app.services import whatsapp

    chamadas = []

    async def _fake_get_credentials(db, tenant_id, provider):
        return {"phone_number_id": "123", "access_token": "tok"}

    async def _fake_registrar_uso(db, tenant_id, provider, sucesso, detalhe=None):
        chamadas.append({"sucesso": sucesso, "detalhe": detalhe})

    monkeypatch.setattr(whatsapp.integration_hub, "get_credentials", _fake_get_credentials)
    monkeypatch.setattr(whatsapp.integration_hub, "registrar_uso", _fake_registrar_uso)
    _FakeAsyncClient.responses = [_FakeResponse(401, "template ausente"), _FakeResponse(401, "token invalido")]
    original = whatsapp.httpx.AsyncClient
    whatsapp.httpx.AsyncClient = _FakeAsyncClient
    try:
        ok = asyncio.run(whatsapp.enviar_whatsapp(None, "t1", "11999998888", "texto"))
    finally:
        whatsapp.httpx.AsyncClient = original

    assert ok is False
    assert len(chamadas) == 1
    assert chamadas[0]["sucesso"] is False
    assert "401" in chamadas[0]["detalhe"]


def test_envio_com_excecao_de_rede_registra_falha(monkeypatch):
    from app.services import whatsapp

    chamadas = []

    async def _fake_get_credentials(db, tenant_id, provider):
        return {"phone_number_id": "123", "access_token": "tok"}

    async def _fake_registrar_uso(db, tenant_id, provider, sucesso, detalhe=None):
        chamadas.append({"sucesso": sucesso, "detalhe": detalhe})

    class _FakeAsyncClientQuebrado:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            raise RuntimeError("timeout de rede")

    monkeypatch.setattr(whatsapp.integration_hub, "get_credentials", _fake_get_credentials)
    monkeypatch.setattr(whatsapp.integration_hub, "registrar_uso", _fake_registrar_uso)
    original = whatsapp.httpx.AsyncClient
    whatsapp.httpx.AsyncClient = _FakeAsyncClientQuebrado
    try:
        ok = asyncio.run(whatsapp.enviar_whatsapp(None, "t1", "11999998888", "texto"))
    finally:
        whatsapp.httpx.AsyncClient = original

    assert ok is False
    assert chamadas == [{"sucesso": False, "detalhe": "timeout de rede"}]


def test_sem_credencial_nao_chama_registrar_uso(monkeypatch):
    """Sem TenantIntegration conectada nem chega a ter o que registrar."""
    from app.services import whatsapp

    chamado = {"registrar_uso": False}

    async def _fake_get_credentials(db, tenant_id, provider):
        return None

    async def _fake_registrar_uso(*a, **kw):
        chamado["registrar_uso"] = True

    monkeypatch.setattr(whatsapp.integration_hub, "get_credentials", _fake_get_credentials)
    monkeypatch.setattr(whatsapp.integration_hub, "registrar_uso", _fake_registrar_uso)

    ok = asyncio.run(whatsapp.enviar_whatsapp(None, "t1", "11999998888", "texto"))

    assert ok is False
    assert chamado["registrar_uso"] is False
