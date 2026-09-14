"""Fase pós-265 — as bases PÚBLICAS (jurisprudência/legislação/doutrina
compartilhada) sempre resolvem pro provedor padrão do sistema, por desenho
(um vetor Gemini não é comparável a um vetor OpenAI). O problema não era o
desenho — era que uma pipeline podia falhar em 100% dos itens e ninguém no
sistema ficava sabendo:

- `finalizar_sync(..., "OK", ...)` era incondicional: `processados: 0,
  falhas: 200` era gravado como sucesso;
- `brain_infra` descartava `processados`/`falhas` do `stats`, então nem o
  SUPERADMIN via;
- a mensagem de `EmbeddingProviderUnavailable` listava TODOS os provedores
  com embeddings ("gemini, openai") mesmo no ramo onde só `openai` serve —
  mandando um tenant só-Gemini cadastrar Gemini pra resolver algo que Gemini
  não resolve.
"""
import pytest


async def _nada():
    return None

import app.rag.embeddings as emb_mod
from app.config import settings


# ─── Status honesto nas 2 pipelines de base pública ──────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("modulo, funcao", [
    ("app.workers.tasks.legislacao_sync", "executar_sync_legislacao"),
    ("app.workers.tasks.jurisprudencia_sync", "executar_sync_stj"),
])
async def test_pipeline_publica_que_falha_em_tudo_nao_termina_OK(monkeypatch, modulo, funcao):
    """Prova central: com a ingestão falhando em todos os itens, o SyncRun
    final precisa sair `ERRO`. Antes era `OK` incondicional."""
    import importlib
    mod = importlib.import_module(modulo)

    chamadas = []

    async def _fake_iniciar_sync(db, tenant_id, fonte, tipo):
        return type("Run", (), {"tenant_id": tenant_id})()

    async def _fake_finalizar_sync(db, run, status, stats):
        chamadas.append((status, stats))

    monkeypatch.setattr("app.services.movements_import.iniciar_sync", _fake_iniciar_sync)
    monkeypatch.setattr("app.services.movements_import.finalizar_sync", _fake_finalizar_sync)

    # A ingestão de cada item estoura — é o cenário real de provedor de
    # embeddings indisponível pras collections públicas.
    async def _ingest_quebrado(**kwargs):
        raise RuntimeError("Busca vetorial indisponível: OPENAI_API_KEY não configurada.")

    monkeypatch.setattr("app.rag.ingestion.ingest_document", _ingest_quebrado)

    db = _FakeDB()
    if funcao == "executar_sync_legislacao":
        async def _fake_lote(*a, **k):
            return [{"urn": "urn:lex:br:federal:lei:2020;14000"}]

        async def _fake_norma(registro):
            return {"texto": "Art. 1º ...", "titulo": "Lei 14.000", "tipo_norma": "LEI"}

        # Os imports são lazy DENTRO da função — patchar no módulo de
        # origem é o único jeito de interceptá-los.
        monkeypatch.setattr("app.integrations.lexml.client.buscar_lote_legislacao_federal", _fake_lote)
        monkeypatch.setattr("app.integrations.lexml.client.buscar_norma_completa", _fake_norma)
    else:
        async def _fake_lote(*a, **k):
            return [{
                "fonte_documento_id": "doc-1", "texto": "Ementa de teste.",
                "tribunal": "STJ", "metadata": {},
            }]

        monkeypatch.setattr("app.integrations.jurisprudencia.stj_client.buscar_lote_recente", _fake_lote)
        # Sem chamada real de LLM: a classificação é fail-soft e opcional.
        monkeypatch.setattr(mod, "classificar_acordao", lambda texto: _nada())

    try:
        await getattr(mod, funcao)(db)
    except Exception:
        # A pipeline pode propagar no caminho de erro externo; o que importa
        # é o status gravado, não o retorno.
        pass

    assert chamadas, "finalizar_sync nunca foi chamado"
    status_final, stats_final = chamadas[-1]
    assert status_final == "ERRO", f"esperava ERRO, veio {status_final} com {stats_final}"


class _FakeResult:
    def __init__(self, itens=None, escalar=None):
        self._itens = itens or []
        self._escalar = escalar

    def scalars(self):
        return self

    def all(self):
        return self._itens

    def scalar_one_or_none(self):
        return self._escalar

    def first(self):
        return self._escalar


class _FakeDB:
    """Sessão mínima: qualquer SELECT devolve vazio (nada já ingerido), e
    add/flush/commit são no-op."""
    def __init__(self):
        self.commits = 0

    async def execute(self, *a, **k):
        return _FakeResult()

    def add(self, obj):
        pass

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


# ─── Mensagem certa por caminho ──────────────────────────────────────────────

def _sem_chave_nenhuma(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    emb_mod._client = None
    monkeypatch.setattr(emb_mod, "_resolve_embedding_credentials", lambda: (None, None, None))
    monkeypatch.setattr(emb_mod, "_resolve_byok_openai_key", lambda: (None, None))


def test_mensagem_de_base_publica_nao_sugere_provedor_incompativel(monkeypatch):
    """No ramo das collections compartilhadas, a mensagem não pode mandar o
    usuário cadastrar Gemini — só o provedor padrão do sistema serve ali."""
    _sem_chave_nenhuma(monkeypatch)

    with pytest.raises(emb_mod.EmbeddingProviderUnavailable) as exc:
        emb_mod.get_embeddings_client(force_system_default=True)

    texto = str(exc.value).lower()
    assert "gemini" not in texto
    assert "compartilhad" in texto
    assert emb_mod.SYSTEM_DEFAULT_PROVIDER in texto


def test_mensagem_do_caminho_byok_continua_listando_os_provedores(monkeypatch):
    """Regressão: no caminho normal (collection privada), a lista dinâmica de
    provedores com embeddings continua valendo — é informação correta ali."""
    _sem_chave_nenhuma(monkeypatch)

    with pytest.raises(emb_mod.EmbeddingProviderUnavailable) as exc:
        emb_mod.get_embeddings_client(force_system_default=False)

    texto = str(exc.value).lower()
    assert "gemini" in texto
    assert "minha ia" in texto
