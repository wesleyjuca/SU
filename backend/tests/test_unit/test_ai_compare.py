"""Fase 137.5 — POST /me/ai-configs/compare: valida entrada (2-5 configs,
prompt não vazio/não gigante, configs do próprio usuário e ativas) e devolve
os resultados de `call_llm_parallel` mesclados com os metadados da config
(nunca a credencial). Mesmo truque de fake `cryptography` de
`test_ai_config_create_validation.py` (bug de sandbox, não afeta produção)."""
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


class _FakeConfig:
    def __init__(self, provider="anthropic", model="claude-sonnet-5", user_id=None, enabled=True,
                 credentials_enc='ENC:{"api_key": "sk-teste"}', display_name="Minha IA"):
        self.id = uuid.uuid4()
        self.provider = provider
        self.model = model
        self.user_id = user_id
        self.enabled = enabled
        self.credentials_enc = credentials_enc
        self.display_name = display_name
        self.base_url = None


class _FakeDB:
    def __init__(self, get_map):
        self._get_map = get_map

    async def get(self, model, obj_id):
        return self._get_map.get((model, obj_id))


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()


@pytest.mark.asyncio
async def test_compare_exige_pelo_menos_2_configs():
    from fastapi import HTTPException
    from app.api.v1.users import compare_my_ai_configs, AICompareRequest

    user = _FakeUser()
    db = _FakeDB({})
    body = AICompareRequest(prompt="oi", config_ids=[str(uuid.uuid4())])

    with pytest.raises(HTTPException) as exc:
        await compare_my_ai_configs(body, current_user=user, db=db)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_compare_rejeita_mais_de_5_configs():
    from fastapi import HTTPException
    from app.api.v1.users import compare_my_ai_configs, AICompareRequest

    user = _FakeUser()
    db = _FakeDB({})
    body = AICompareRequest(prompt="oi", config_ids=[str(uuid.uuid4()) for _ in range(6)])

    with pytest.raises(HTTPException) as exc:
        await compare_my_ai_configs(body, current_user=user, db=db)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_compare_rejeita_prompt_vazio():
    from fastapi import HTTPException
    from app.api.v1.users import compare_my_ai_configs, AICompareRequest

    user = _FakeUser()
    db = _FakeDB({})
    body = AICompareRequest(prompt="   ", config_ids=[str(uuid.uuid4()), str(uuid.uuid4())])

    with pytest.raises(HTTPException) as exc:
        await compare_my_ai_configs(body, current_user=user, db=db)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_compare_rejeita_config_de_outro_usuario():
    from fastapi import HTTPException
    from app.api.v1.users import compare_my_ai_configs, AICompareRequest
    from app.models.ai_config import AIProviderConfig

    user = _FakeUser()
    minha = _FakeConfig(user_id=user.id)
    de_outro = _FakeConfig(user_id=uuid.uuid4())
    db = _FakeDB({
        (AIProviderConfig, minha.id): minha,
        (AIProviderConfig, de_outro.id): de_outro,
    })
    body = AICompareRequest(prompt="oi", config_ids=[str(minha.id), str(de_outro.id)])

    with pytest.raises(HTTPException) as exc:
        await compare_my_ai_configs(body, current_user=user, db=db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_compare_rejeita_config_desativada():
    from fastapi import HTTPException
    from app.api.v1.users import compare_my_ai_configs, AICompareRequest
    from app.models.ai_config import AIProviderConfig

    user = _FakeUser()
    ativa = _FakeConfig(user_id=user.id, enabled=True)
    desativada = _FakeConfig(user_id=user.id, enabled=False)
    db = _FakeDB({
        (AIProviderConfig, ativa.id): ativa,
        (AIProviderConfig, desativada.id): desativada,
    })
    body = AICompareRequest(prompt="oi", config_ids=[str(ativa.id), str(desativada.id)])

    with pytest.raises(HTTPException) as exc:
        await compare_my_ai_configs(body, current_user=user, db=db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_compare_devolve_resultados_mesclados_com_metadados_da_config(monkeypatch):
    from app.api.v1.users import compare_my_ai_configs, AICompareRequest
    from app.models.ai_config import AIProviderConfig
    import app.integrations.llm_client as llm_client_mod

    user = _FakeUser()
    c1 = _FakeConfig(provider="anthropic", model="claude-sonnet-5", user_id=user.id, display_name="Claude")
    c2 = _FakeConfig(provider="deepseek", model="deepseek-chat", user_id=user.id, display_name="DeepSeek")
    db = _FakeDB({
        (AIProviderConfig, c1.id): c1,
        (AIProviderConfig, c2.id): c2,
    })

    async def _fake_call_llm_parallel(configs, messages, system="", max_tokens=2048, temperature=0.3):
        assert len(configs) == 2
        assert messages[0]["content"] == "compare isso"
        return [
            {"provider": "anthropic", "model": "claude-sonnet-5", "content": "resposta 1",
             "input_tokens": 5, "output_tokens": 10, "cost_usd": 0.001, "latency_ms": 120, "error": None},
            {"provider": "deepseek", "model": "deepseek-chat", "content": None,
             "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "latency_ms": 50, "error": "falhou"},
        ]
    monkeypatch.setattr(llm_client_mod, "call_llm_parallel", _fake_call_llm_parallel)

    body = AICompareRequest(prompt="compare isso", config_ids=[str(c1.id), str(c2.id)])
    result = await compare_my_ai_configs(body, current_user=user, db=db)

    assert len(result["results"]) == 2
    assert result["results"][0]["display_name"] == "Claude"
    assert result["results"][0]["content"] == "resposta 1"
    assert result["results"][1]["display_name"] == "DeepSeek"
    assert result["results"][1]["error"] == "falhou"
    # nunca inclui credencial
    assert all("credentials_enc" not in r and "api_key" not in r for r in result["results"])
