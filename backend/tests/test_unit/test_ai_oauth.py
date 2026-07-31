"""Fase 137.2 — OAuth genuíno pro OpenRouter ("Conectar com login").

Mesmo truque de `test_integration_hub_oauth.py`: injeta um `cryptography.fernet`
fake em `sys.modules` antes do import (bug conhecido do sandbox, não afeta
produção/CI, que tem o pacote real instalado e funcional)."""
import asyncio
import base64
import hashlib
import inspect
import sys
import types
import uuid
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


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class _FakeAsyncClient:
    next_response = None
    raise_exc = None

    def __init__(self, timeout=None):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        if _FakeAsyncClient.raise_exc:
            raise _FakeAsyncClient.raise_exc
        return _FakeAsyncClient.next_response


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ScalarsListResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        class _S:
            def __init__(self, v):
                self._v = v

            def all(self):
                return self._v
        return _S(self._values)


class _FakeSession:
    """Devolve os resultados de `execute()` na ordem chamada; `get()` é
    resolvido por um dict {(Model, id): obj}."""
    def __init__(self, execute_results=None, get_map=None):
        self._results = list(execute_results or [])
        self._i = 0
        self._get_map = get_map or {}
        self.added = []
        self.flushed = False
        self.committed = False

    async def execute(self, stmt):
        r = self._results[self._i]
        self._i += 1
        return r

    async def get(self, model, obj_id):
        return self._get_map.get((model, obj_id))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed = True

    async def commit(self):
        self.committed = True


def test_sign_and_verify_state_roundtrip():
    from app.api.v1 import ai_oauth

    uid = str(uuid.uuid4())
    state = ai_oauth._sign_state(uid, "verifier-abc")
    claims = ai_oauth._verify_state(state)
    assert claims["sub"] == uid
    assert claims["code_verifier"] == "verifier-abc"
    assert "config_id" not in claims


def test_sign_state_com_config_id():
    from app.api.v1 import ai_oauth

    uid = str(uuid.uuid4())
    cid = str(uuid.uuid4())
    state = ai_oauth._sign_state(uid, "verifier-xyz", config_id=cid)
    claims = ai_oauth._verify_state(state)
    assert claims["config_id"] == cid


def test_verify_state_purpose_errado_rejeita():
    from fastapi import HTTPException
    from jose import jwt
    from app.api.v1 import ai_oauth
    from app.config import settings

    bad_state = jwt.encode(
        {"sub": "u1", "code_verifier": "v1", "purpose": "outra_coisa",
         "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
        settings.SECRET_KEY, algorithm="HS256",
    )
    try:
        ai_oauth._verify_state(bad_state)
        assert False, "deveria ter levantado HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400


def test_verify_state_expirado_rejeita():
    from fastapi import HTTPException
    from jose import jwt
    from app.api.v1 import ai_oauth
    from app.config import settings

    expired_state = jwt.encode(
        {"sub": "u1", "code_verifier": "v1", "purpose": "openrouter_oauth",
         "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.SECRET_KEY, algorithm="HS256",
    )
    try:
        ai_oauth._verify_state(expired_state)
        assert False, "deveria ter levantado HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400


def test_code_challenge_bate_com_valor_esperado_sha256_base64url():
    from app.api.v1 import ai_oauth

    verifier = "um-code-verifier-conhecido-para-teste"
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("utf-8")).digest()).rstrip(b"=").decode("ascii")
    assert ai_oauth._code_challenge(verifier) == expected
    assert "=" not in ai_oauth._code_challenge(verifier)


def test_connect_endpoint_exige_auth_via_depends_get_current_user():
    from app.api.v1 import ai_oauth
    from app.dependencies import get_current_user

    sig = inspect.signature(ai_oauth.openrouter_oauth_connect)
    dep = sig.parameters["current_user"].default
    assert dep.dependency is get_current_user


def test_callback_endpoint_nao_exige_auth():
    from app.api.v1 import ai_oauth

    sig = inspect.signature(ai_oauth.openrouter_oauth_callback)
    assert "current_user" not in sig.parameters


def test_callback_cria_config_nova_quando_sem_config_id():
    from app.api.v1 import ai_oauth
    from app.models.ai_config import AIProviderConfig

    user_id = uuid.uuid4()
    state = ai_oauth._sign_state(str(user_id), "verifier-1")

    _FakeAsyncClient.next_response = _FakeResponse({"key": "sk-or-novo"})
    _FakeAsyncClient.raise_exc = None
    original_client = ai_oauth.httpx.AsyncClient
    ai_oauth.httpx.AsyncClient = _FakeAsyncClient

    class _FakeUser:
        id = user_id
        tenant_id = uuid.uuid4()

    session = _FakeSession(execute_results=[
        _ScalarsListResult([]),          # existentes (nenhuma config ainda)
        None,                              # UPDATE unset-defaults (is_default=True, existentes vazio mas roda igual)
        _ScalarResult(_FakeUser()),       # busca do User pra tenant_id
    ])

    try:
        resp = asyncio.run(ai_oauth.openrouter_oauth_callback(code="auth-code-1", state=state, db=session))
    finally:
        ai_oauth.httpx.AsyncClient = original_client

    assert "openrouter_ok" in resp.headers["location"]
    assert len(session.added) == 1
    novo = session.added[0]
    assert isinstance(novo, AIProviderConfig)
    assert novo.provider == "openrouter"
    assert novo.auth_method == "oauth"
    assert novo.is_default is True
    assert session.committed is True


def test_callback_atualiza_config_existente_quando_config_id_presente():
    from app.api.v1 import ai_oauth
    from app.models.ai_config import AIProviderConfig

    user_id = uuid.uuid4()
    config_id = uuid.uuid4()
    state = ai_oauth._sign_state(str(user_id), "verifier-2", config_id=str(config_id))

    _FakeAsyncClient.next_response = _FakeResponse({"key": "sk-or-atualizada"})
    _FakeAsyncClient.raise_exc = None
    original_client = ai_oauth.httpx.AsyncClient
    ai_oauth.httpx.AsyncClient = _FakeAsyncClient

    existing = AIProviderConfig()
    existing.id = config_id
    existing.user_id = user_id
    existing.provider = "openrouter"
    existing.auth_method = "api_key"
    existing.credentials_enc = "ENC:{}"
    existing.status = "ERRO"
    existing.last_error = "chave antiga inválida"

    session = _FakeSession(get_map={(AIProviderConfig, config_id): existing})

    try:
        resp = asyncio.run(ai_oauth.openrouter_oauth_callback(code="auth-code-2", state=state, db=session))
    finally:
        ai_oauth.httpx.AsyncClient = original_client

    assert "openrouter_ok" in resp.headers["location"]
    assert session.added == []  # não cria config nova, atualiza a existente
    assert existing.auth_method == "oauth"
    assert existing.status == "ATIVA"
    assert existing.last_error is None


def test_callback_falha_na_troca_redireciona_com_erro_sem_quebrar():
    from app.api.v1 import ai_oauth

    user_id = uuid.uuid4()
    state = ai_oauth._sign_state(str(user_id), "verifier-3")

    _FakeAsyncClient.raise_exc = RuntimeError("timeout falando com openrouter.ai")
    original_client = ai_oauth.httpx.AsyncClient
    ai_oauth.httpx.AsyncClient = _FakeAsyncClient

    session = _FakeSession()

    try:
        resp = asyncio.run(ai_oauth.openrouter_oauth_callback(code="auth-code-3", state=state, db=session))
    finally:
        ai_oauth.httpx.AsyncClient = original_client
        _FakeAsyncClient.raise_exc = None

    assert "openrouter_erro" in resp.headers["location"]
    assert session.added == []
    assert session.committed is False
