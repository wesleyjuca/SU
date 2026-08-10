"""Fase 168 — "Testar conexão" era um no-op silencioso pro WhatsApp:
`_fonte_credenciada_do_provider()` só reconhecia pdpj/escavador/judit/
jusbrasil, então o teste sempre devolvia "não disponível" sem checar a
credencial de verdade. `testar_credenciais()` faz uma sonda leve (GET no
próprio phone_number_id) que distingue token válido de inválido/expirado,
sem enviar mensagem nenhuma."""
import sys
import types

import pytest


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
    next_response = None

    def __init__(self, timeout=None):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        return _FakeAsyncClient.next_response


@pytest.mark.asyncio
async def test_testar_credenciais_sucesso():
    from app.services import whatsapp

    _FakeAsyncClient.next_response = _FakeResponse(200)
    original = whatsapp.httpx.AsyncClient
    whatsapp.httpx.AsyncClient = _FakeAsyncClient
    try:
        ok, detail = await whatsapp.testar_credenciais("tok_valido", "123")
    finally:
        whatsapp.httpx.AsyncClient = original

    assert ok is True
    assert detail == "ok"


@pytest.mark.asyncio
async def test_testar_credenciais_token_invalido():
    from app.services import whatsapp

    _FakeAsyncClient.next_response = _FakeResponse(401, "Invalid OAuth access token")
    original = whatsapp.httpx.AsyncClient
    whatsapp.httpx.AsyncClient = _FakeAsyncClient
    try:
        ok, detail = await whatsapp.testar_credenciais("tok_expirado", "123")
    finally:
        whatsapp.httpx.AsyncClient = original

    assert ok is False
    assert "inválido" in detail or "expirado" in detail


@pytest.mark.asyncio
async def test_testar_credenciais_sem_credenciais_nao_chama_rede():
    from app.services import whatsapp

    ok, detail = await whatsapp.testar_credenciais(None, None)

    assert ok is False
    assert "incompletas" in detail


@pytest.mark.asyncio
async def test_fonte_credenciada_do_provider_reconhece_whatsapp(monkeypatch):
    from app.services import integration_hub as ih

    async def _fake_get_credentials(db, tenant_id, provider):
        assert provider == "whatsapp"
        return {"access_token": "tok", "phone_number_id": "999"}

    monkeypatch.setattr(ih, "get_credentials", _fake_get_credentials)

    fonte = await ih._fonte_credenciada_do_provider(None, "t1", "whatsapp")

    assert fonte is not None
    assert isinstance(fonte, ih._WhatsAppFonteTeste)


@pytest.mark.asyncio
async def test_fonte_credenciada_do_provider_whatsapp_sem_credenciais_devolve_none(monkeypatch):
    from app.services import integration_hub as ih

    async def _fake_get_credentials(db, tenant_id, provider):
        return None

    monkeypatch.setattr(ih, "get_credentials", _fake_get_credentials)

    fonte = await ih._fonte_credenciada_do_provider(None, "t1", "whatsapp")

    assert fonte is None


@pytest.mark.asyncio
async def test_testar_conexao_whatsapp_marca_erro_com_token_invalido(monkeypatch):
    from app.services import integration_hub as ih

    class _FakeInteg:
        credentials_enc = "algumacoisa"
        status = "CONECTADA"
        last_success_at = None
        last_error_at = None
        last_error_detail = None

    integ = _FakeInteg()

    async def _fake_get_integration(db, tenant_id, provider):
        return integ

    class _FakeFonte:
        async def testar(self):
            return (False, "token inválido ou expirado")

    async def _fake_fonte_credenciada(db, tenant_id, provider):
        return _FakeFonte()

    monkeypatch.setattr(ih, "get_integration", _fake_get_integration)
    monkeypatch.setattr(ih, "_fonte_credenciada_do_provider", _fake_fonte_credenciada)

    class _FakeDBFlush:
        async def flush(self):
            pass

    resultado = await ih.testar_conexao(_FakeDBFlush(), "t1", "whatsapp")

    assert resultado["ok"] is False
    assert integ.status == "ERRO"
    assert integ.last_error_detail == "token inválido ou expirado"
