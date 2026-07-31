"""Fase 137.3 — bug corrigido no caminho: `POST /me/ai-configs` exigia
"Informe a URL do servidor" pra Anthropic também, porque a checagem usava
`not info["base_url"]` (True pra Anthropic — usa SDK próprio, nunca lê
base_url — E pra Ollama — self-hosted, precisa de URL própria) sem
distinguir os dois motivos. Bloqueava cadastrar qualquer IA Anthropic via
BYOK multi-provedor desde a Fase 137.1. Mesmo truque de fake `cryptography`
de `test_integration_hub_oauth.py`/`test_ai_oauth.py` (bug de sandbox, não
afeta produção)."""
import sys
import types
import uuid
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


class _RowsResult:
    def scalars(self):
        class _S:
            def all(self):
                return []
        return _S()


class _FakeDB:
    def __init__(self):
        self.added = []

    async def execute(self, stmt):
        return _RowsResult()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


class _FakeUser:
    id = uuid.uuid4()
    tenant_id = uuid.uuid4()


@pytest.mark.asyncio
async def test_criar_config_anthropic_sem_base_url_nao_exige_url():
    from app.api.v1.users import create_my_ai_config, AIConfigCreate

    db = _FakeDB()
    body = AIConfigCreate(provider="anthropic", api_key="sk-ant-teste")
    result = await create_my_ai_config(body, current_user=_FakeUser(), db=db)

    assert result["provider"] == "anthropic"
    assert db.added[0].base_url is None


@pytest.mark.asyncio
async def test_criar_config_ollama_sem_base_url_ainda_exige_url():
    """Regressão: a correção não pode ter removido a exigência real do Ollama."""
    from fastapi import HTTPException
    from app.api.v1.users import create_my_ai_config, AIConfigCreate

    db = _FakeDB()
    body = AIConfigCreate(provider="ollama")
    with pytest.raises(HTTPException) as exc:
        await create_my_ai_config(body, current_user=_FakeUser(), db=db)

    assert exc.value.status_code == 422
    assert db.added == []


@pytest.mark.asyncio
async def test_criar_config_gemini_usa_base_url_fixa_sem_exigir_do_usuario():
    from app.api.v1.users import create_my_ai_config, AIConfigCreate

    db = _FakeDB()
    body = AIConfigCreate(provider="gemini", api_key="sk-gem-teste")
    result = await create_my_ai_config(body, current_user=_FakeUser(), db=db)

    assert result["provider"] == "gemini"
    assert db.added[0].base_url  # veio da registry, não do usuário
