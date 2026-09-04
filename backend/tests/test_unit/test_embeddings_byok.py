"""Achado real (validação pós-merge da Fase 258/259): `_resolve_byok_openai_key`
(`app/rag/embeddings.py`) só considerava a config de IA PADRÃO/primária do
usuário (`ai_creds_ctx`) — um usuário com Anthropic como padrão (o comum,
já que é o provedor usado no resto do sistema) e uma chave OpenAI cadastrada
só como config SECUNDÁRIA (`ai_fallback_ctx`, a cadeia de fallback que
`user_ai_creds()` já expõe) nunca tinha essa chave considerada aqui, mesmo
com uma OpenAI válida cadastrada — a Pesquisa Jurídica (RAG) continuava
exigindo `OPENAI_API_KEY` central mesmo quando o usuário já tinha resolvido
o problema do jeito certo (cadastrando uma chave OpenAI em "Minha IA")."""
import pytest

from app.integrations.llm_client import ai_creds_ctx, ai_fallback_ctx
from app.rag.embeddings import _resolve_byok_openai_key


@pytest.fixture(autouse=True)
def _limpa_contextvars():
    tok1 = ai_creds_ctx.set(None)
    tok2 = ai_fallback_ctx.set(None)
    yield
    ai_creds_ctx.reset(tok1)
    ai_fallback_ctx.reset(tok2)


def test_sem_nenhuma_config_devolve_none():
    assert _resolve_byok_openai_key() == (None, None)


def test_primaria_openai_e_usada_diretamente():
    ai_creds_ctx.set({"provider": "openai", "api_key": "sk-primaria", "base_url": None})
    assert _resolve_byok_openai_key() == ("sk-primaria", None)


def test_primaria_anthropic_sem_fallback_devolve_none():
    ai_creds_ctx.set({"provider": "anthropic", "api_key": "sk-ant-primaria", "base_url": None})
    assert _resolve_byok_openai_key() == (None, None)


def test_primaria_anthropic_com_openai_no_fallback_e_encontrada():
    """O cenário real do achado: Anthropic como padrão, OpenAI só como
    config secundária habilitada — antes do fix isso sempre falhava."""
    ai_creds_ctx.set({"provider": "anthropic", "api_key": "sk-ant-primaria", "base_url": None})
    ai_fallback_ctx.set([
        {"provider": "gemini", "api_key": "gm-secundaria", "base_url": None},
        {"provider": "openai", "api_key": "sk-fallback", "base_url": None},
    ])
    assert _resolve_byok_openai_key() == ("sk-fallback", None)


def test_primaria_vence_mesmo_com_openai_no_fallback():
    """Se a PRÓPRIA primária já é openai, o fallback nem precisa ser
    percorrido — preserva a prioridade original do usuário."""
    ai_creds_ctx.set({"provider": "openai", "api_key": "sk-primaria-openai", "base_url": None})
    ai_fallback_ctx.set([{"provider": "openai", "api_key": "sk-fallback-openai", "base_url": None}])
    assert _resolve_byok_openai_key() == ("sk-primaria-openai", None)


def test_openai_sem_api_key_no_fallback_e_ignorada():
    ai_creds_ctx.set({"provider": "anthropic", "api_key": "sk-ant", "base_url": None})
    ai_fallback_ctx.set([{"provider": "openai", "api_key": "", "base_url": None}])
    assert _resolve_byok_openai_key() == (None, None)


def test_base_url_customizado_e_preservado():
    ai_creds_ctx.set({"provider": "anthropic", "api_key": "sk-ant", "base_url": None})
    ai_fallback_ctx.set([{"provider": "openai", "api_key": "sk-fallback", "base_url": "https://proxy.exemplo.com/v1"}])
    assert _resolve_byok_openai_key() == ("sk-fallback", "https://proxy.exemplo.com/v1")


def test_nenhum_provider_openai_em_lugar_nenhum_devolve_none():
    ai_creds_ctx.set({"provider": "anthropic", "api_key": "sk-ant", "base_url": None})
    ai_fallback_ctx.set([{"provider": "gemini", "api_key": "gm", "base_url": None}])
    assert _resolve_byok_openai_key() == (None, None)
