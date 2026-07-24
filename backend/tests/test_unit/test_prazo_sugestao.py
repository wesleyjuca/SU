"""Fase 91 — sugestão de prazo por IA (parsing puro, sem chamar o LLM de verdade)."""
import pytest

from app.services.prazo_sugestao import parse_sugestao, sugerir_prazo, TIPOS_VALIDOS


def test_parse_sugestao_json_valido():
    texto = '{"tipo": "CONTESTACAO", "dias": 15, "dias_uteis": true, "confianca": "alta", "justificativa": "Citação para contestar."}'
    s = parse_sugestao(texto)
    assert s == {
        "tipo": "CONTESTACAO", "dias": 15, "dias_uteis": True,
        "confianca": "alta", "justificativa": "Citação para contestar.",
    }


def test_parse_sugestao_tipo_invalido_vira_outros():
    texto = '{"tipo": "TIPO_INVENTADO", "dias": 10, "confianca": "media", "justificativa": "x"}'
    s = parse_sugestao(texto)
    assert s["tipo"] == "OUTROS"


def test_parse_sugestao_dias_fora_do_range_clampado():
    texto = '{"tipo": "RECURSO", "dias": 9999, "confianca": "alta", "justificativa": "x"}'
    assert parse_sugestao(texto)["dias"] == 180
    texto2 = '{"tipo": "RECURSO", "dias": 0, "confianca": "alta", "justificativa": "x"}'
    assert parse_sugestao(texto2)["dias"] == 1


def test_parse_sugestao_confianca_invalida_vira_baixa():
    texto = '{"tipo": "RECURSO", "dias": 10, "confianca": "certeza absoluta", "justificativa": "x"}'
    assert parse_sugestao(texto)["confianca"] == "baixa"


def test_parse_sugestao_com_cerca_markdown():
    texto = '```json\n{"tipo": "EMBARGOS", "dias": 5, "confianca": "alta", "justificativa": "x"}\n```'
    s = parse_sugestao(texto)
    assert s["tipo"] == "EMBARGOS"
    assert s["dias"] == 5


def test_parse_sugestao_json_quebrado_retorna_none():
    assert parse_sugestao("isso não é JSON") is None
    assert parse_sugestao("") is None


def test_todos_tipos_validos_batem_com_frontend():
    assert TIPOS_VALIDOS == {
        "CONTESTACAO", "RECURSO", "MANIFESTACAO", "EMBARGOS", "CONTRARRAZOES", "CUMPRIMENTO", "OUTROS",
    }


@pytest.mark.asyncio
async def test_sugerir_prazo_texto_vazio_nao_chama_llm():
    resultado = await sugerir_prazo("", None, None)
    assert resultado == {"ok": False, "detail": "Intimação sem texto para analisar."}


@pytest.mark.asyncio
async def test_sugerir_prazo_llm_falha_e_fail_soft(monkeypatch):
    import app.integrations.llm_client as llm_client

    async def _falha(*a, **k):
        raise RuntimeError("sem chave de API")

    monkeypatch.setattr(llm_client, "call_llm", _falha)

    resultado = await sugerir_prazo("Intime-se para contestar.", "Intimação", "TJSP")
    assert resultado["ok"] is False
    assert "detail" in resultado


@pytest.mark.asyncio
async def test_sugerir_prazo_llm_ok_repassa_sugestao(monkeypatch):
    import app.integrations.llm_client as llm_client

    async def _ok(*a, **k):
        return ('{"tipo": "CONTESTACAO", "dias": 15, "confianca": "alta", "justificativa": "x"}', 10, 20, 0.001)

    monkeypatch.setattr(llm_client, "call_llm", _ok)

    resultado = await sugerir_prazo("Intime-se para contestar.", "Intimação", "TJSP")
    assert resultado["ok"] is True
    assert resultado["tipo"] == "CONTESTACAO"
    assert resultado["dias"] == 15
