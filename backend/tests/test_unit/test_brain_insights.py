"""Fase 85 — Cérebro inteligente: parsing/montagem de contexto (lógica pura).

Fase 204 — gerar_insights() passou a envolver a chamada ao LLM em
user_ai_creds() (fix do achado da Fase 203: rota sem fallback BYOK, ao
contrário de toda outra rota disparadora de IA do sistema)."""
from contextlib import asynccontextmanager

import pytest

from app.services import brain_insights as bi


@asynccontextmanager
async def _noop_user_ai_creds(session, user_id, task_type=None):
    """Fake de user_ai_creds() pros testes que não exercitam BYOK em si —
    só confirma que gerar_insights() entra no context manager antes de
    chamar o LLM, sem aplicar nenhuma credencial real."""
    yield


# ─── parse_insights ────────────────────────────────────────────────────────────
def test_parse_json_dentro_de_cerca_markdown():
    texto = """Análise:
```json
[{"tipo":"risco","titulo":"T1","descricao":"D1","prioridade":"media","area":"captura"},
 {"tipo":"erro","titulo":"T2","descricao":"D2","prioridade":"alta","area":"infra"}]
```"""
    out = bi.parse_insights(texto)
    assert len(out) == 2
    assert out[0]["tipo"] == "risco" and out[1]["prioridade"] == "alta"


def test_parse_json_puro_sem_cerca():
    texto = '[{"tipo":"melhoria","titulo":"X","descricao":"Y","prioridade":"baixa","area":"cerebro"}]'
    out = bi.parse_insights(texto)
    assert len(out) == 1 and out[0]["prioridade"] == "baixa"


def test_tipo_e_prioridade_invalidos_caem_no_default():
    texto = '[{"tipo":"lixo","titulo":"T","descricao":"D","prioridade":"lixo","area":"a"}]'
    out = bi.parse_insights(texto)
    assert out[0]["tipo"] == "melhoria" and out[0]["prioridade"] == "media"


def test_item_malformado_e_descartado_sem_afetar_os_demais():
    texto = '[{"tipo":"erro"}, {"tipo":"risco","titulo":"T","descricao":"D","prioridade":"alta","area":"x"}]'
    out = bi.parse_insights(texto)
    assert len(out) == 1 and out[0]["titulo"] == "T"


def test_resposta_fora_do_formato_vira_fallback_1_insight():
    texto = "Não consegui gerar JSON, mas aqui vai minha análise em texto livre."
    out = bi.parse_insights(texto)
    assert len(out) == 1 and out[0]["descricao"].startswith("Não consegui")


def test_resposta_vazia_e_array_vazio():
    assert bi.parse_insights("") == []
    assert bi.parse_insights("   ") == []
    assert bi.parse_insights("[]") == []


# ─── montar_contexto / gerar_insights (mocks) ─────────────────────────────────
@pytest.mark.asyncio
async def test_montar_contexto_agrega_partes_nao_vazias(monkeypatch):
    async def _mapa():
        return "MAPA DO SISTEMA (por camada):\n- nucleo: API FastAPI"
    async def _infra():
        return "SAÚDE DE INFRAESTRUTURA:\n{}"
    async def _logs():
        return ""  # uma parte vazia não deve aparecer no contexto final
    async def _metricas():
        return "MÉTRICAS POR ESCRITÓRIO (plataforma):\n{}"
    monkeypatch.setattr(bi, "_resumo_mapa", _mapa)
    monkeypatch.setattr(bi, "_resumo_infra", _infra)
    monkeypatch.setattr(bi, "_resumo_logs", _logs)
    monkeypatch.setattr(bi, "_resumo_metricas", _metricas)

    ctx = await bi.montar_contexto()
    assert "MAPA DO SISTEMA" in ctx and "SAÚDE DE INFRAESTRUTURA" in ctx and "MÉTRICAS POR ESCRITÓRIO" in ctx
    assert ctx.count("\n\n") == 2  # só 3 partes não-vazias juntadas


@pytest.mark.asyncio
async def test_gerar_insights_contexto_vazio_nao_chama_llm(monkeypatch):
    async def _vazio():
        return ""
    monkeypatch.setattr(bi, "montar_contexto", _vazio)
    r = await bi.gerar_insights(db=None, user_id="u1")
    assert r["ok"] is False and r["insights"] == []


@pytest.mark.asyncio
async def test_gerar_insights_fluxo_feliz(monkeypatch):
    async def _ctx():
        return "MAPA DO SISTEMA...\n\nSAÚDE DE INFRAESTRUTURA..."
    monkeypatch.setattr(bi, "montar_contexto", _ctx)

    async def fake_call_llm(messages, system="", max_tokens=2048, temperature=0.3):
        assert system.strip() != ""
        assert messages[0]["content"] == await _ctx()
        return ('[{"tipo":"evolucao","titulo":"T","descricao":"D","prioridade":"baixa","area":"x"}]', 10, 5, 0.001)

    import app.integrations.byok as byok_mod
    import app.integrations.llm_client as llm
    monkeypatch.setattr(llm, "call_llm", fake_call_llm)
    monkeypatch.setattr(byok_mod, "user_ai_creds", _noop_user_ai_creds)

    r = await bi.gerar_insights(db=None, user_id="u1")
    assert r["ok"] is True and len(r["insights"]) == 1 and r["custo_usd"] == 0.001


@pytest.mark.asyncio
async def test_gerar_insights_entra_no_contexto_byok_antes_de_chamar_llm(monkeypatch):
    """Fase 204 — confirma que gerar_insights() efetivamente entra em
    user_ai_creds() (não só chama call_llm direto, como o código quebrado
    fazia antes do fix)."""
    async def _ctx():
        return "algum contexto"
    monkeypatch.setattr(bi, "montar_contexto", _ctx)

    chamadas = []

    @asynccontextmanager
    async def _tracking_user_ai_creds(session, user_id, task_type=None):
        chamadas.append((session, user_id, task_type))
        yield

    async def fake_call_llm(*a, **k):
        assert chamadas, "call_llm foi chamado sem passar por user_ai_creds() antes"
        return ("[]", 1, 1, 0.0)

    import app.integrations.byok as byok_mod
    import app.integrations.llm_client as llm
    monkeypatch.setattr(llm, "call_llm", fake_call_llm)
    monkeypatch.setattr(byok_mod, "user_ai_creds", _tracking_user_ai_creds)

    r = await bi.gerar_insights(db="fake_db", user_id="u42")
    assert r["ok"] is True
    assert chamadas == [("fake_db", "u42", "brain_insights")]


@pytest.mark.asyncio
async def test_gerar_insights_llm_falha_nao_levanta(monkeypatch):
    async def _ctx():
        return "algum contexto"
    monkeypatch.setattr(bi, "montar_contexto", _ctx)

    async def fake_call_llm_falha(*a, **k):
        raise RuntimeError("sem API key")

    import app.integrations.byok as byok_mod
    import app.integrations.llm_client as llm
    monkeypatch.setattr(llm, "call_llm", fake_call_llm_falha)
    monkeypatch.setattr(byok_mod, "user_ai_creds", _noop_user_ai_creds)

    r = await bi.gerar_insights(db=None, user_id="u1")
    assert r["ok"] is False and "detail" in r
