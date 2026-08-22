"""Cérebro inteligente — insights proativos (Fase 85).

Dá ao Cérebro "inteligência própria" sobre o sistema: monta um retrato
compacto (mapa de módulos por camada + logs recentes de aviso/erro + métricas
por escritório + saúde de infra) e pede a um LLM um diagnóstico estruturado —
melhorias, erros, riscos e sugestões de evolução — baseado SOMENTE nesse
contexto (nunca inventado).

Não é streaming (é uma análise pontual, não uma conversa) — usa
`call_llm` não-streaming, o mesmo cliente multi-provider do assistente do
Cérebro. Fail-soft em toda parte: cada trecho de contexto que falhar vira
string vazia; se o LLM ou o parsing falharem, o chamador recebe um erro claro
em vez de um 500."""
from __future__ import annotations

import json
import re

import structlog

log = structlog.get_logger()

TIPOS_VALIDOS = {"melhoria", "erro", "risco", "evolucao"}
PRIORIDADES_VALIDAS = {"alta", "media", "baixa"}

SYSTEM_PROMPT = """Você é o núcleo de autoanálise do sistema AFJ CORE — uma IA que conhece a
própria arquitetura e monitora a própria saúde. Você recebe um retrato do sistema
(mapa de módulos por camada, logs recentes, métricas por escritório, saúde de
infraestrutura) e produz um diagnóstico honesto e acionável para o SuperAdmin.

Responda APENAS com um array JSON válido (nada de texto antes ou depois), neste
formato exato:
[{"tipo": "melhoria|erro|risco|evolucao", "titulo": "...", "descricao": "...",
  "prioridade": "alta|media|baixa", "area": "..."}]

Regras:
- Baseie-se SOMENTE no contexto fornecido — NUNCA invente números, erros, módulos
  ou tribunais que não estejam explicitamente no contexto.
- "erro": problema já observável (aparece nos logs de aviso/erro ou nas métricas).
- "risco": algo que pode dar errado mesmo sem ter dado ainda (ex.: fonte com
  circuit breaker aberto, escritório sem atividade recente, infra indisponível).
- "melhoria": qualidade, organização ou débito técnico visível no mapa do sistema.
- "evolucao": próximo passo natural, dado o que já existe (não repita o óbvio).
- Gere entre 2 e 8 itens, os mais relevantes agora — não force quantidade.
- Se o contexto realmente não tiver nada digno de nota, responda [].
- Responda em português do Brasil, de forma objetiva e técnica."""


async def _resumo_mapa() -> str:
    try:
        from app.services.system_map import construir_mapa
        mapa = construir_mapa()
        por_camada: dict[str, list[str]] = {}
        for no in mapa["nos"]:
            por_camada.setdefault(no.get("camada", "?"), []).append(no["label"])
        linhas = [f"- {camada} ({len(labels)}): {', '.join(labels)}" for camada, labels in por_camada.items()]
        return "MAPA DO SISTEMA (por camada):\n" + "\n".join(linhas)
    except Exception as exc:
        log.warning("insights_resumo_mapa_falhou", error=str(exc))
        return ""


async def _resumo_logs() -> str:
    try:
        from app.core.log_buffer import snapshot
        eventos = snapshot(limit=30, level="warning")
        if not eventos:
            return "LOGS RECENTES: nenhum aviso ou erro no buffer atual."
        linhas = [f"- [{e['level']}] {e['event']}" for e in eventos]
        return "LOGS RECENTES (avisos/erros, mais recentes primeiro):\n" + "\n".join(linhas)
    except Exception as exc:
        log.warning("insights_resumo_logs_falhou", error=str(exc))
        return ""


async def _resumo_metricas() -> str:
    try:
        from app.services.brain_metrics import coletar_metricas
        m = await coletar_metricas()
        if not m.get("ok"):
            return ""
        compacto = {
            "totais": m.get("totais"),
            "escritorios": [
                {"nome": t["nome"], "processos": t["processos"], "agent_runs_24h": t["agent_runs_24h"],
                 "usuarios_ativos": t["usuarios_ativos"], "ativo": t["ativo"]}
                for t in (m.get("tenants") or [])[:20]
            ],
        }
        return "MÉTRICAS POR ESCRITÓRIO (plataforma):\n" + json.dumps(compacto, ensure_ascii=False)[:2000]
    except Exception as exc:
        log.warning("insights_resumo_metricas_falhou", error=str(exc))
        return ""


async def _resumo_infra() -> str:
    try:
        from app.services.brain_infra import coletar_infra
        snap = await coletar_infra()
        compacto = {
            "celery": snap.get("celery", {}).get("ok"),
            "redis": snap.get("redis", {}).get("ok"),
            "qdrant": snap.get("qdrant", {}).get("ok"),
            "fontes": [
                {"nome": f.get("nome"), "breaker": f.get("breaker")}
                for f in (snap.get("fontes", {}) or {}).get("fontes", [])
            ],
        }
        return "SAÚDE DE INFRAESTRUTURA:\n" + json.dumps(compacto, ensure_ascii=False)[:1000]
    except Exception as exc:
        log.warning("insights_resumo_infra_falhou", error=str(exc))
        return ""


async def montar_contexto() -> str:
    """Concatena as partes do retrato do sistema (só as que não vierem vazias)."""
    partes = [await _resumo_mapa(), await _resumo_infra(), await _resumo_logs(), await _resumo_metricas()]
    return "\n\n".join(p for p in partes if p)


def _extrair_json(texto: str) -> list | None:
    """Extrai o array JSON da resposta do modelo — tolerante a cerca de markdown
    (```json ... ```) e a texto antes/depois do array."""
    if not texto:
        return None
    limpo = texto.strip()
    match_cerca = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", limpo, re.DOTALL)
    candidato = match_cerca.group(1) if match_cerca else limpo
    if not match_cerca:
        inicio, fim = candidato.find("["), candidato.rfind("]")
        if inicio == -1 or fim == -1 or fim < inicio:
            return None
        candidato = candidato[inicio:fim + 1]
    try:
        dados = json.loads(candidato)
        return dados if isinstance(dados, list) else None
    except Exception:
        return None


def parse_insights(texto: str) -> list[dict]:
    """Converte a resposta bruta do LLM em insights válidos. Itens malformados
    são descartados individualmente (não derrubam os demais); se o parsing
    inteiro falhar, devolve 1 insight com o texto bruto (fallback nunca-vazio
    quando o modelo respondeu algo, mesmo fora do formato)."""
    dados = _extrair_json(texto)
    if dados is None:
        bruto = (texto or "").strip()
        if not bruto:
            return []
        return [{
            "tipo": "melhoria", "titulo": "Resposta do modelo (formato inesperado)",
            "descricao": bruto[:1000], "prioridade": "media", "area": "cérebro",
        }]

    out: list[dict] = []
    for item in dados:
        if not isinstance(item, dict):
            continue
        titulo = str(item.get("titulo") or "").strip()
        descricao = str(item.get("descricao") or "").strip()
        if not titulo or not descricao:
            continue
        tipo = str(item.get("tipo") or "").strip().lower()
        prioridade = str(item.get("prioridade") or "").strip().lower()
        out.append({
            "tipo": tipo if tipo in TIPOS_VALIDOS else "melhoria",
            "titulo": titulo[:200],
            "descricao": descricao[:1500],
            "prioridade": prioridade if prioridade in PRIORIDADES_VALIDAS else "media",
            "area": str(item.get("area") or "geral")[:80],
        })
    return out


async def gerar_insights(db, user_id) -> dict:
    """Monta o contexto, chama o LLM e devolve `{ok, insights, custo_usd}` ou
    `{ok: False, detail}` em caso de falha (contexto vazio ou erro do LLM).

    Fase 204 — ao contrário de toda outra rota disparadora de IA do sistema,
    esta chamava `call_llm` direto, sem nunca entrar em `user_ai_creds()`
    (`app/integrations/byok.py`): dependia 100% da `ANTHROPIC_API_KEY` do
    servidor, sem nenhum fallback pra IA própria do usuário (nem a do
    próprio SUPERADMIN que clicou no botão). `db`/`user_id` agora envolvem a
    chamada com o mesmo mecanismo BYOK usado por generate_petition/
    review_document/manage_contract."""
    contexto = await montar_contexto()
    if not contexto:
        return {"ok": False, "insights": [], "detail": "Não foi possível montar o contexto do sistema."}

    try:
        from app.integrations.byok import user_ai_creds
        from app.integrations.llm_client import call_llm
        async with user_ai_creds(db, user_id, "brain_insights"):
            conteudo, _in_tok, _out_tok, custo = await call_llm(
                messages=[{"role": "user", "content": contexto}],
                system=SYSTEM_PROMPT,
                max_tokens=2048,
                temperature=0.3,
            )
    except Exception as exc:
        log.warning("insights_llm_falhou", error=str(exc))
        return {"ok": False, "insights": [], "detail": f"Falha ao consultar o modelo: {exc}"[:300]}

    insights = parse_insights(conteudo)
    return {"ok": True, "insights": insights, "custo_usd": custo}
