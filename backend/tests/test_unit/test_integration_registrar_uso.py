"""Fase 165 — `TenantIntegration.last_success_at`/`last_error_at`. Antes, só o
clique manual em "Testar conexão" atualizava `status`; uma integração podia
ficar morta há semanas com a UI ainda mostrando CONECTADA. `registrar_uso()`
é chamado em todo uso REAL da credencial (WhatsApp, Gmail/Agenda, PDPJ/
Escavador/Judit/Jusbrasil) — nunca só no teste manual.

Mesmo truque de `test_integration_hub_oauth.py`: injeta um `cryptography.fernet`
fake em `sys.modules` antes do import (bug conhecido do PyO3 neste sandbox)."""
import asyncio
import sys
import types
from datetime import datetime, timedelta, timezone


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


class _FakeIntegRow:
    def __init__(self):
        self.tenant_id = "t1"
        self.provider = "whatsapp"
        self.status = "CONECTADA"
        self.last_success_at = None
        self.last_error_at = None
        self.last_error_detail = None


class _FakeDB:
    def __init__(self, integ):
        self._integ = integ
        self.commits = 0

    class _ScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    async def execute(self, _query):
        return _FakeDB._ScalarResult(self._integ)

    async def commit(self):
        self.commits += 1


def test_registrar_uso_sucesso_marca_last_success_at_e_status_conectada():
    from app.services import integration_hub as ih

    integ = _FakeIntegRow()
    integ.status = "ERRO"  # estado anterior, deve ser corrigido pra CONECTADA
    db = _FakeDB(integ)
    asyncio.run(ih.registrar_uso(db, "t1", "whatsapp", sucesso=True))

    assert integ.status == "CONECTADA"
    assert integ.last_success_at is not None
    assert db.commits == 1


def test_registrar_uso_falha_marca_last_error_at_status_erro_e_detalhe():
    from app.services import integration_hub as ih

    integ = _FakeIntegRow()
    db = _FakeDB(integ)
    asyncio.run(ih.registrar_uso(db, "t1", "whatsapp", sucesso=False, detalhe="HTTP 401: token expirado"))

    assert integ.status == "ERRO"
    assert integ.last_error_at is not None
    assert integ.last_error_detail == "HTTP 401: token expirado"
    assert db.commits == 1


def test_registrar_uso_trunca_detalhe_em_500_chars():
    from app.services import integration_hub as ih

    integ = _FakeIntegRow()
    db = _FakeDB(integ)
    detalhe_gigante = "x" * 900
    asyncio.run(ih.registrar_uso(db, "t1", "whatsapp", sucesso=False, detalhe=detalhe_gigante))

    assert len(integ.last_error_detail) == 500


def test_registrar_uso_sem_integracao_conectada_e_no_op():
    from app.services import integration_hub as ih

    db = _FakeDB(None)
    asyncio.run(ih.registrar_uso(db, "t1", "whatsapp", sucesso=True))

    assert db.commits == 0  # nada pra atualizar — não deve commitar à toa


def test_registrar_uso_nunca_propaga_excecao_fail_soft():
    """Um erro no meio do registro (ex.: DB fora do ar) não pode derrubar o
    fluxo principal (envio de WhatsApp/e-mail que já terminou com sucesso)."""
    from app.services import integration_hub as ih

    class _DbQuebrado:
        async def execute(self, _query):
            raise RuntimeError("conexão perdida")

    # Não deve lançar.
    asyncio.run(ih.registrar_uso(_DbQuebrado(), "t1", "whatsapp", sucesso=True))


def test_testar_conexao_falha_marca_last_error_at_e_detalhe(monkeypatch):
    from app.services import integration_hub as ih

    integ = _FakeIntegRow()
    integ.credentials_enc = "algumacoisa"

    class _FakeFonte:
        async def testar(self):
            return (False, "credencial expirada")

    async def _fake_get_integration(db, tenant_id, provider):
        return integ

    async def _fake_fonte_credenciada(db, tenant_id, provider):
        return _FakeFonte()

    monkeypatch.setattr(ih, "get_integration", _fake_get_integration)
    monkeypatch.setattr(ih, "_fonte_credenciada_do_provider", _fake_fonte_credenciada)

    class _FakeDBFlush:
        async def flush(self):
            pass

    resultado = asyncio.run(ih.testar_conexao(_FakeDBFlush(), "t1", "pdpj"))

    assert resultado["ok"] is False
    assert integ.status == "ERRO"
    assert integ.last_error_at is not None
    assert integ.last_error_detail == "credencial expirada"


def test_testar_conexao_sucesso_marca_last_success_at(monkeypatch):
    from app.services import integration_hub as ih

    integ = _FakeIntegRow()
    integ.credentials_enc = "algumacoisa"

    class _FakeFonte:
        async def testar(self):
            return (True, "ok")

    async def _fake_get_integration(db, tenant_id, provider):
        return integ

    async def _fake_fonte_credenciada(db, tenant_id, provider):
        return _FakeFonte()

    monkeypatch.setattr(ih, "get_integration", _fake_get_integration)
    monkeypatch.setattr(ih, "_fonte_credenciada_do_provider", _fake_fonte_credenciada)

    class _FakeDBFlush:
        async def flush(self):
            pass

    resultado = asyncio.run(ih.testar_conexao(_FakeDBFlush(), "t1", "pdpj"))

    assert resultado["ok"] is True
    assert integ.status == "CONECTADA"
    assert integ.last_success_at is not None


def test_refresh_oauth_sem_refresh_token_registra_falha(monkeypatch):
    """Antes desta fase o status ficava CONECTADA pra sempre nesse caso —
    sem refresh_token o token expirado nunca vai se renovar sozinho."""
    from app.services import integration_hub as ih

    chamadas = []

    async def _fake_registrar_uso(db, tenant_id, provider, sucesso, detalhe=None):
        chamadas.append({"tenant_id": tenant_id, "provider": provider, "sucesso": sucesso, "detalhe": detalhe})

    monkeypatch.setattr(ih, "registrar_uso", _fake_registrar_uso)

    class _FakeInteg:
        tenant_id = "t1"

    passado = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    creds = {"__oauth__": True, "access_token": "tok_velho", "oauth_refresh_token": None, "oauth_expires_at": passado}
    asyncio.run(ih._refresh_oauth_if_needed(None, _FakeInteg(), "mercadopago", creds))

    assert len(chamadas) == 1
    assert chamadas[0]["sucesso"] is False
    assert chamadas[0]["provider"] == "mercadopago"


def test_refresh_oauth_falha_de_rede_registra_falha(monkeypatch):
    from app.services import integration_hub as ih

    chamadas = []

    async def _fake_registrar_uso(db, tenant_id, provider, sucesso, detalhe=None):
        chamadas.append(sucesso)

    async def fake_refresh_falha(provider, refresh_token):
        raise RuntimeError("timeout")

    monkeypatch.setattr(ih, "registrar_uso", _fake_registrar_uso)
    monkeypatch.setattr(ih, "_exchange_oauth_refresh", fake_refresh_falha)

    class _FakeInteg:
        tenant_id = "t1"

    passado = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    creds = {"__oauth__": True, "access_token": "tok_velho", "oauth_refresh_token": "r1", "oauth_expires_at": passado}
    asyncio.run(ih._refresh_oauth_if_needed(None, _FakeInteg(), "mercadopago", creds))

    assert chamadas == [False]


def test_refresh_oauth_sucesso_nao_chama_registrar_uso_mas_seta_last_success_at(monkeypatch):
    """Sucesso já seta `last_success_at` direto (tem `integ` em mãos, não
    precisa da query redundante de `registrar_uso`)."""
    from app.services import integration_hub as ih

    chamado = {"registrar_uso": False}

    async def _fake_registrar_uso(*a, **kw):
        chamado["registrar_uso"] = True

    async def fake_refresh(provider, refresh_token):
        return {"access_token": "tok_novo", "refresh_token": "r2", "expires_in": 3600}

    monkeypatch.setattr(ih, "registrar_uso", _fake_registrar_uso)
    monkeypatch.setattr(ih, "_exchange_oauth_refresh", fake_refresh)

    class _FakeDB:
        async def flush(self):
            pass

    class _FakeInteg:
        tenant_id = "t1"
        credentials_enc = None
        status = None
        last_success_at = None

    passado = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    creds = {"__oauth__": True, "access_token": "tok_velho", "oauth_refresh_token": "r1", "oauth_expires_at": passado}
    integ = _FakeInteg()
    asyncio.run(ih._refresh_oauth_if_needed(_FakeDB(), integ, "mercadopago", creds))

    assert chamado["registrar_uso"] is False
    assert integ.status == "CONECTADA"
    assert integ.last_success_at is not None
