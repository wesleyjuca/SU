"""Assistente administrativo do Cérebro (Bloco F / F5).

Responde perguntas do SUPERADMIN sobre o sistema. Monta o contexto com:
1. FATOS DO SISTEMA (conhecimento curado, sempre disponível);
2. snapshot de infra em tempo real (services/brain_infra);
3. RAG opcional na coleção `documentacao_sistema` (best-effort — só se Qdrant
   e embeddings estiverem configurados).

Streaming via llm_client.call_llm_stream. Guardrail de custo antes de chamar.
"""
from __future__ import annotations

import json
import os

import structlog

log = structlog.get_logger()

# Conhecimento curado sobre a arquitetura (a "documentação viva" mínima que o
# assistente sempre tem, mesmo sem Qdrant). Mantido conciso e factual.
SYSTEM_FACTS = """VOCÊ É O ASSISTENTE ADMINISTRATIVO DO SISTEMA AFJ CORE (SuperAdmin).

Arquitetura:
- Backend FastAPI (Python 3.12), frontend Next.js 14 (App Router), PostgreSQL (SQLAlchemy async),
  Redis (cache + fila Celery), Qdrant (RAG de jurisprudência/documentos), Celery (worker + beat).
- Multi-tenant: todo dado tem tenant_id; papéis: SUPERADMIN (dono da plataforma), ADMIN, SOCIO,
  GESTOR, ADVOGADO, PARALEGAL, ASSISTENTE, CLIENT.
- IA: camada multi-provider (Anthropic Claude / Google Gemini) com BYOK por usuário; 19 agentes
  orquestrados por LangGraph (brain/orchestrator); HITL — ações críticas criam Approval PENDENTE
  e não executam até aprovação humana.

Captura de processos:
- Descoberta por OAB via Comunica/DJEN (pública, nacional, obrigatória por Res. CNJ 455/2022).
- Enriquecimento por número via DataJud público (metadados + movimentos; NÃO expõe partes).
- Importador único de movimentos (dedup canônico), SyncRun registra cada sincronização.

Integrações (hub, credenciais cifradas por escritório): Stripe/Mercado Pago (pagamento),
Clicksign (assinatura), WhatsApp (Meta). Google Workspace por usuário (OAuth).

Segurança: JWT + refresh; audit_log imutável; bloqueio suave por inadimplência.

REGRAS: seja objetivo e técnico. Baseie-se nos FATOS, no SNAPSHOT DE INFRA e nos TRECHOS DE
DOCUMENTAÇÃO fornecidos. Se algo não estiver no contexto, diga que não tem a informação — NUNCA
invente números, endpoints ou estado de serviços. Responda em português."""


async def _rag_docs(pergunta: str) -> str:
    """Trechos da coleção documentacao_sistema (best-effort; vazio se indisponível).

    Fase pós-260.3 — achado real: este guard checava só `settings.
    OPENAI_API_KEY` (chave central), então um SUPERADMIN com BYOK openai
    cadastrado (sem chave central configurada) nunca via o RAG do Cérebro
    funcionar — mesma classe de bug já corrigida em `rag/embeddings.py`
    (Fase pós-259), nunca aplicada aqui. Removida a checagem de chave
    aqui — `retrieve()` → `embed_text()` já resolve BYOK sozinho (chamador,
    `responder_stream`, precisa estar dentro do `user_ai_creds()` pro
    contextvar existir); se nenhuma chave (central ou BYOK) estiver
    disponível, a exceção sobe e é engolida pelo `except` abaixo, igual
    já acontecia pra qualquer outra falha de RAG (best-effort)."""
    try:
        from app.config import settings
        configurado = bool(
            settings.QDRANT_API_KEY or
            (settings.QDRANT_URL and settings.QDRANT_URL not in {"http://qdrant:6333", "http://localhost:6333"})
        )
        if not configurado:
            return ""
        from app.db.qdrant import get_qdrant
        from app.rag.retrieval import retrieve
        q = await get_qdrant()
        hits = await retrieve(q, pergunta, collections=["documentacao_sistema"], k=4)
        if not hits:
            return ""
        linhas = [f"- {h.get('text', '')[:600]}" for h in hits]
        return "TRECHOS DE DOCUMENTAÇÃO (RAG):\n" + "\n".join(linhas)
    except Exception as exc:
        log.warning("brain_assistant_rag_failed", error=str(exc))
        return ""


async def _infra_resumo(db) -> str:
    """Snapshot de infra em texto compacto para o contexto do modelo."""
    try:
        from app.services.brain_infra import coletar_infra
        snap = await coletar_infra()
        compacto = {
            "celery": snap.get("celery", {}),
            "redis_ok": snap.get("redis", {}).get("ok"),
            "qdrant": snap.get("qdrant", {}),
            "postgres_pool": snap.get("postgres_pool", {}),
            "jobs": snap.get("jobs", {}),
        }
        return "SNAPSHOT DE INFRA (tempo real):\n" + json.dumps(compacto, ensure_ascii=False)[:1500]
    except Exception:
        return ""


async def montar_system_prompt(db, pergunta: str) -> str:
    partes = [SYSTEM_FACTS]
    infra = await _infra_resumo(db)
    if infra:
        partes.append(infra)
    docs = await _rag_docs(pergunta)
    if docs:
        partes.append(docs)
    return "\n\n".join(partes)


async def responder_stream(db, historico: list[dict], pergunta: str, user_id=None):
    """Gerador assíncrono que emite ("delta", txt) e ("done", {...}).

    `historico` = mensagens anteriores [{role, content}]; `pergunta` = nova
    mensagem do usuário (já incluída no fim de historico pelo chamador OU passada
    aqui). Monta o system prompt com fatos + infra + RAG.

    Fase 226 — achado do usuário ("assistente não funciona"), mesma classe de
    bug da Fase 204.A (`brain_insights.py`): esta chamava `call_llm_stream`
    direto, sem nunca entrar em `user_ai_creds()` — dependia 100% da
    `ANTHROPIC_API_KEY`/`GEMINI_API_KEY` do servidor, sem fallback pra IA
    própria do SUPERADMIN que está conversando. `user_id` agora envolve a
    chamada com o mesmo mecanismo BYOK usado por generate_petition/
    review_document/manage_contract/gerar_insights.

    Sessão PRÓPRIA (não a `db` recebida) pra resolver as credenciais: `db`
    aqui vem de `Depends(get_db)` do endpoint (`system.py::brain_assistant`),
    que a essa altura já foi fechada pelo FastAPI — a resposta é um
    `StreamingResponse`, e a limpeza da dependência roda assim que a função
    do endpoint retorna, antes do generator (este aqui) começar a ser
    consumido. Mesma armadilha já documentada no próprio arquivo pra
    persistir a resposta do assistente ("sessão nova — o generator roda
    após o request") — `db` nunca era usada de fato até este fix (`_infra_
    resumo`/`_rag_docs` não fazem query nenhuma com ela), por isso o risco
    nunca tinha se manifestado antes.

    Fase pós-260.3 — achado real: `montar_system_prompt()` (que chama
    `_rag_docs()`, que gera embeddings) rodava ANTES de entrar no bloco
    `user_ai_creds()` abaixo — o contextvar de credencial BYOK nunca
    estava setado quando o RAG do Cérebro tentava embeddar a pergunta,
    então mesmo depois do fix em `_rag_docs()` (guard removido) o BYOK
    nunca era realmente alcançado. Movido pra dentro do `async with`."""
    from app.db.base import AsyncSessionLocal
    from app.integrations.byok import user_ai_creds
    from app.integrations.llm_client import call_llm_stream

    # limita o histórico p/ não estourar contexto/custo
    mensagens = [{"role": m["role"], "content": m["content"]} for m in historico][-12:]

    async with AsyncSessionLocal() as creds_db, user_ai_creds(creds_db, user_id, "brain_assistant"):
        system = await montar_system_prompt(db, pergunta)
        async for evento in call_llm_stream(mensagens, system=system, max_tokens=2048, temperature=0.2):
            yield evento


# ─── Reindexação da documentação do sistema ──────────────────────────────────
_DOC_FILES = ["CLAUDE.md", "DEPLOY.md", "DEPLOY_VPS.md", "MOBILE.md", "README.md"]


async def reindexar_documentacao(user_id=None) -> dict:
    """Indexa os markdown de documentação na coleção documentacao_sistema.
    Best-effort: exige Qdrant + alguma chave OpenAI (central ou BYOK do
    usuário que disparou) pra gerar os embeddings. Retorna contagem.

    Fase pós-260.3 — achado real: mesma classe de bug de `_rag_docs()` —
    só checava `settings.OPENAI_API_KEY` central, ignorando BYOK. `user_id`
    (o SUPERADMIN que chamou `POST /system/brain/assistant/reindex`) agora
    envolve toda a indexação em `user_ai_creds()`, igual `responder_stream`."""
    from app.config import settings
    from app.db.base import AsyncSessionLocal
    from app.integrations.byok import user_ai_creds
    try:
        from app.rag.embeddings import _resolve_byok_openai_key
        from app.rag.ingestion import ingest_document
    except Exception as exc:
        return {"ok": False, "motivo": f"ingestão indisponível: {exc}"}

    # raiz do repo (backend/ está um nível abaixo)
    raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    indexados = 0
    async with AsyncSessionLocal() as creds_db, user_ai_creds(creds_db, user_id, "brain_assistant_reindex"):
        byok_key, _ = _resolve_byok_openai_key()
        if not byok_key and not settings.OPENAI_API_KEY:
            return {"ok": False, "motivo": "Nenhuma chave OpenAI disponível (central ou BYOK) — necessária p/ embeddings."}
        for nome in _DOC_FILES:
            caminho = os.path.join(raiz, nome)
            if not os.path.exists(caminho):
                continue
            try:
                with open(caminho, encoding="utf-8") as f:
                    texto = f.read()
                await ingest_document(
                    content=texto,
                    collection="documentacao_sistema",
                    metadata={"fonte": nome},
                    document_id=f"doc-{nome}",
                )
                indexados += 1
            except Exception as exc:
                log.warning("reindex_doc_failed", arquivo=nome, error=str(exc))
    return {"ok": True, "arquivos_indexados": indexados}
