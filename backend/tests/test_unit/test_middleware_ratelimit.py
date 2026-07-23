"""Bloco F / F7 — rate-limit do assistente do Cérebro (lógica pura, sem Redis).

Cobre `_user_identifier` (extração do identificador por usuário a partir do JWT,
com fallback gracioso) e a presença/forma da regra `brain_assistant`.
"""
import sys
import types

from app.core import middleware as mw


class _FakeRequest:
    """Request mínima: só precisa de .headers.get('authorization', '')."""
    def __init__(self, auth: str | None = None):
        self.headers = {"authorization": auth} if auth is not None else {}


def test_regra_brain_assistant_existe_e_e_por_usuario():
    assert "brain_assistant" in mw.RATE_LIMIT_RULES
    limite, janela = mw.RATE_LIMIT_RULES["brain_assistant"]
    assert limite == 15 and janela == 60
    # É mais restritiva que o default (protege o LLM contra abuso/custo).
    assert limite < mw.RATE_LIMIT_RULES["default"][0]
    assert mw.BRAIN_ASSISTANT_PATH == "/api/v1/system/brain/assistant"


def test_user_identifier_sem_auth_usa_fallback():
    assert mw._user_identifier(_FakeRequest(), "1.2.3.4") == "1.2.3.4"


def test_user_identifier_token_invalido_usa_fallback():
    # Token lixo → parsing falha (ou jose ausente) → cai no fallback, sem erro.
    assert mw._user_identifier(_FakeRequest("Bearer nao-e-um-jwt"), "9.9.9.9") == "9.9.9.9"


def test_user_identifier_extrai_jti_do_jwt(monkeypatch):
    # Stub do jose p/ rodar sem a dependência instalada (CI tem; sandbox não).
    fake_jose = types.ModuleType("jose")
    fake_jwt = types.SimpleNamespace(
        get_unverified_claims=lambda _t: {"jti": "sessao-123", "sub": "user-abc"}
    )
    fake_jose.jwt = fake_jwt
    monkeypatch.setitem(sys.modules, "jose", fake_jose)

    ident = mw._user_identifier(_FakeRequest("Bearer qualquer.coisa.aqui"), "0.0.0.0")
    assert ident == "sessao-123"  # jti tem prioridade sobre sub


def test_user_identifier_cai_para_sub_sem_jti(monkeypatch):
    fake_jose = types.ModuleType("jose")
    fake_jose.jwt = types.SimpleNamespace(
        get_unverified_claims=lambda _t: {"sub": "user-abc"}
    )
    monkeypatch.setitem(sys.modules, "jose", fake_jose)

    ident = mw._user_identifier(_FakeRequest("Bearer x.y.z"), "0.0.0.0")
    assert ident == "user-abc"
