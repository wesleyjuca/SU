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
    """Trechos da coleção documentacao_sistema (best-effort; vazio se indisponível)."""
    try:
        from app.config import settings
        configurado = bool(
            settings.QDRANT_API_KEY or
            (settings.QDRANT_URL and settings.QDRANT_URL not in {"http://qdrant:6333", "http://localhost:6333"})
        )
        if not configurado or not settings.OPENAI_API_KEY:
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


async def responder_stream(db, historico: list[dict], pergunta: str):
    """Gerador assíncrono que emite ("delta", txt) e ("done", {...}).

    `historico` = mensagens anteriores [{role, content}]; `pergunta` = nova
    mensagem do usuário (já incluída no fim de historico pelo chamador OU passada
    aqui). Monta o system prompt com fatos + infra + RAG."""
    from app.integrations.llm_client import call_llm_stream

    system = await montar_system_prompt(db, pergunta)
    # limita o histórico p/ não estourar contexto/custo
    mensagens = [{"role": m["role"], "content": m["content"]} for m in historico][-12:]

    async for evento in call_llm_stream(mensagens, system=system, max_tokens=2048, temperature=0.2):
        yield evento


# ─── Reindexação da documentação do sistema ──────────────────────────────────
_DOC_FILES = ["CLAUDE.md", "DEPLOY.md", "DEPLOY_VPS.md", "MOBILE.md", "README.md"]


async def reindexar_documentacao() -> dict:
    """Indexa os markdown de documentação na coleção documentacao_sistema.
    Best-effort: exige Qdrant + OPENAI_API_KEY (embeddings). Retorna contagem."""
    from app.config import settings
    if not settings.OPENAI_API_KEY:
        return {"ok": False, "motivo": "OPENAI_API_KEY ausente (necessária p/ embeddings)"}
    try:
        from app.rag.ingestion import ingest_document
    except Exception as exc:
        return {"ok": False, "motivo": f"ingestão indisponível: {exc}"}

    # raiz do repo (backend/ está um nível abaixo)
    raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    indexados = 0
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
