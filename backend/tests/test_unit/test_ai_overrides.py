"""Fase 137.4 — "ajuste por área" (`PUT /me/ai-settings/overrides`) passa a
aceitar `provider_config_id` (uma IA inteira pra essa tarefa), não só uma
string de `model` (caminho legado). Mesmo truque de fake `cryptography` de
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


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        rows = self._rows

        class _S:
            def all(self):
                return rows
        return _S()


class _FakeDB:
    def __init__(self, *execute_results, get_map=None):
        self._results = list(execute_results)
        self._i = 0
        self._get_map = get_map or {}
        self.added = []
        self.deleted = []

    async def execute(self, stmt):
        r = self._results[self._i]
        self._i += 1
        return r

    async def get(self, model, obj_id):
        return self._get_map.get((model, obj_id))

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        pass


class _FakeConfig:
    def __init__(self, provider="anthropic", user_id=None):
        self.id = uuid.uuid4()
        self.provider = provider
        self.user_id = user_id


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()
        self.tenant_id = uuid.uuid4()
        self.ai_provider = None


@pytest.mark.asyncio
async def test_override_com_provider_config_id_da_propria_conta_e_salvo():
    from app.api.v1.users import update_my_ai_overrides, AIOverridesUpdate, AIOverrideItem
    from app.models.ai_config import AIProviderConfig

    user = _FakeUser()
    minha_config = _FakeConfig(provider="deepseek", user_id=user.id)
    db = _FakeDB(
        _ScalarResult(None),  # default_config (nenhuma — não importa pro caminho com provider_config_id)
        _RowsResult([]),      # existing overrides (nada a apagar)
        get_map={(AIProviderConfig, minha_config.id): minha_config},
    )
    body = AIOverridesUpdate(overrides=[
        AIOverrideItem(task_type="analytics_report", provider_config_id=str(minha_config.id)),
    ])

    result = await update_my_ai_overrides(body, current_user=user, db=db)

    assert result["overrides"] == [{"task_type": "analytics_report", "provider_config_id": str(minha_config.id), "model": None}]
    assert len(db.added) == 1
    assert db.added[0].provider_config_id == minha_config.id
    assert db.added[0].model is None


@pytest.mark.asyncio
async def test_override_com_config_de_outro_usuario_e_rejeitado():
    from fastapi import HTTPException
    from app.api.v1.users import update_my_ai_overrides, AIOverridesUpdate, AIOverrideItem
    from app.models.ai_config import AIProviderConfig

    user = _FakeUser()
    config_de_outro = _FakeConfig(provider="deepseek", user_id=uuid.uuid4())
    db = _FakeDB(
        _ScalarResult(None),
        get_map={(AIProviderConfig, config_de_outro.id): config_de_outro},
    )
    body = AIOverridesUpdate(overrides=[
        AIOverrideItem(task_type="generate_petition", provider_config_id=str(config_de_outro.id)),
    ])

    with pytest.raises(HTTPException) as exc:
        await update_my_ai_overrides(body, current_user=user, db=db)

    assert exc.value.status_code == 404
    assert db.added == []


@pytest.mark.asyncio
async def test_override_so_com_model_valida_contra_provider_da_config_padrao():
    from fastapi import HTTPException
    from app.api.v1.users import update_my_ai_overrides, AIOverridesUpdate, AIOverrideItem
    from app.models.ai_config import AIProviderConfig

    user = _FakeUser()
    padrao = _FakeConfig(provider="gemini", user_id=user.id)
    db = _FakeDB(_ScalarResult(padrao))  # default_config real (provider=gemini)
    body = AIOverridesUpdate(overrides=[
        AIOverrideItem(task_type="generate_petition", model="Gemini"),  # formato inválido pra gemini
    ])
    _ = AIProviderConfig  # só documenta o import relevante ao teste

    with pytest.raises(HTTPException) as exc:
        await update_my_ai_overrides(body, current_user=user, db=db)

    assert exc.value.status_code == 422
    assert db.added == []


@pytest.mark.asyncio
async def test_override_com_model_valido_e_salvo_caminho_legado():
    from app.api.v1.users import update_my_ai_overrides, AIOverridesUpdate, AIOverrideItem

    user = _FakeUser()
    padrao = _FakeConfig(provider="gemini", user_id=user.id)
    db = _FakeDB(_ScalarResult(padrao), _RowsResult([]))
    body = AIOverridesUpdate(overrides=[
        AIOverrideItem(task_type="analytics_report", model="gemini-2.5-flash"),
    ])

    result = await update_my_ai_overrides(body, current_user=user, db=db)

    assert result["overrides"] == [{"task_type": "analytics_report", "provider_config_id": None, "model": "gemini-2.5-flash"}]
    assert db.added[0].provider_config_id is None
    assert db.added[0].model == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_override_sem_config_e_sem_model_e_rejeitado():
    from fastapi import HTTPException
    from app.api.v1.users import update_my_ai_overrides, AIOverridesUpdate, AIOverrideItem

    user = _FakeUser()
    db = _FakeDB(_ScalarResult(None))
    body = AIOverridesUpdate(overrides=[AIOverrideItem(task_type="generate_petition")])

    with pytest.raises(HTTPException) as exc:
        await update_my_ai_overrides(body, current_user=user, db=db)

    assert exc.value.status_code == 422
    assert db.added == []


@pytest.mark.asyncio
async def test_override_tipo_de_tarefa_duplicado_e_rejeitado():
    from fastapi import HTTPException
    from app.api.v1.users import update_my_ai_overrides, AIOverridesUpdate, AIOverrideItem

    user = _FakeUser()
    padrao = _FakeConfig(provider="gemini", user_id=user.id)
    db = _FakeDB(_ScalarResult(padrao))
    body = AIOverridesUpdate(overrides=[
        AIOverrideItem(task_type="generate_petition", model="gemini-2.5-flash"),
        AIOverrideItem(task_type="generate_petition", model="gemini-2.5-pro"),
    ])

    with pytest.raises(HTTPException) as exc:
        await update_my_ai_overrides(body, current_user=user, db=db)

    assert exc.value.status_code == 422
    assert "duplicado" in exc.value.detail.lower()
