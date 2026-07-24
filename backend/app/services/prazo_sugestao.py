"""Sugestão de prazo por IA (Fase 91) — prefill do formulário de triagem, nunca cria o prazo.

TRIAGEM/HITL continua intacta: esta função só sugere `tipo`/`dias` a partir do
texto da intimação, pra pré-preencher o modal de `/publicacoes` — quem cria o
`ProcessDeadline` continua sendo o humano, via POST /publicacoes/{id}/triagem.
Fail-soft em toda parte: se o LLM ou o parsing falharem, o chamador recebe
`{"ok": False}` e o formulário simplesmente não é pré-preenchido (o usuário
preenche manualmente, como hoje).
"""
from __future__ import annotations

import json
import re

import structlog

log = structlog.get_logger()

# Mesma lista de `TIPOS_PRAZO` em frontend/src/app/(dashboard)/publicacoes/page.tsx —
# mantida em espelho (lista pequena, baixo custo de sincronizar manualmente).
TIPOS_VALIDOS = {"CONTESTACAO", "RECURSO", "MANIFESTACAO", "EMBARGOS", "CONTRARRAZOES", "CUMPRIMENTO", "OUTROS"}
CONFIANCAS_VALIDAS = {"alta", "media", "baixa"}
DIAS_MIN, DIAS_MAX = 1, 180

SYSTEM_PROMPT = """Você é um assistente jurídico que sugere o tipo de prazo processual e o
número de dias a partir do texto de uma intimação/publicação do Diário de Justiça.

Responda APENAS com um objeto JSON válido (nada de texto antes ou depois), neste
formato exato:
{"tipo": "CONTESTACAO|RECURSO|MANIFESTACAO|EMBARGOS|CONTRARRAZOES|CUMPRIMENTO|OUTROS",
 "dias": 15, "dias_uteis": true, "confianca": "alta|media|baixa", "justificativa": "..."}

Regras:
- "tipo" deve ser EXATAMENTE um dos valores listados acima.
- "dias" é o prazo em dias corridos/úteis conforme a lei processual brasileira aplicável
  ao tipo identificado (ex.: contestação cível padrão = 15 dias úteis, CPC art. 335).
- "confianca": "alta" se o texto deixa claro o tipo de ato exigido; "baixa" se o texto
  for ambíguo ou genérico demais pra ter certeza.
- "justificativa": 1 frase curta explicando o raciocínio (ex.: menciona qual dispositivo
  legal ou tipo de ato).
- Se não for possível identificar nenhum prazo processual no texto (ex.: mero despacho
  de mero expediente, sem exigência de resposta), responda com "tipo": "OUTROS",
  "confianca": "baixa" e explique isso na justificativa — NUNCA invente um prazo.
- Responda em português do Brasil."""


def _extrair_objeto(texto: str) -> dict | None:
    """Extrai o objeto JSON da resposta do modelo — tolerante a cerca de markdown
    (```json ... ```) e a texto antes/depois do objeto."""
    if not texto:
        return None
    limpo = texto.strip()
    match_cerca = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", limpo, re.DOTALL)
    candidato = match_cerca.group(1) if match_cerca else limpo
    if not match_cerca:
        inicio, fim = candidato.find("{"), candidato.rfind("}")
        if inicio == -1 or fim == -1 or fim < inicio:
            return None
        candidato = candidato[inicio:fim + 1]
    try:
        dados = json.loads(candidato)
        return dados if isinstance(dados, dict) else None
    except Exception:
        return None


def parse_sugestao(texto: str) -> dict | None:
    """Converte a resposta bruta do LLM numa sugestão válida, ou None se
    não for possível extrair nada aproveitável."""
    dados = _extrair_objeto(texto)
    if dados is None:
        return None

    tipo = str(dados.get("tipo") or "").strip().upper()
    if tipo not in TIPOS_VALIDOS:
        tipo = "OUTROS"

    try:
        dias = int(dados.get("dias"))
    except (TypeError, ValueError):
        dias = 15
    dias = max(DIAS_MIN, min(DIAS_MAX, dias))

    confianca = str(dados.get("confianca") or "").strip().lower()
    if confianca not in CONFIANCAS_VALIDAS:
        confianca = "baixa"

    return {
        "tipo": tipo,
        "dias": dias,
        "dias_uteis": bool(dados.get("dias_uteis", True)),
        "confianca": confianca,
        "justificativa": str(dados.get("justificativa") or "").strip()[:300],
    }


async def sugerir_prazo(texto_intimacao: str, tipo_comunicacao: str | None, tribunal: str | None) -> dict:
    """Chama o LLM e devolve `{ok, tipo, dias, dias_uteis, confianca, justificativa}`
    ou `{ok: False, detail}` — nunca levanta exceção (fail-soft)."""
    if not (texto_intimacao or "").strip():
        return {"ok": False, "detail": "Intimação sem texto para analisar."}

    contexto = f"TEXTO DA INTIMAÇÃO:\n{texto_intimacao[:4000]}"
    if tipo_comunicacao:
        contexto += f"\n\nTIPO DE COMUNICAÇÃO (DJe): {tipo_comunicacao}"
    if tribunal:
        contexto += f"\nTRIBUNAL: {tribunal}"

    try:
        from app.integrations.llm_client import call_llm
        conteudo, _in_tok, _out_tok, _custo = await call_llm(
            messages=[{"role": "user", "content": contexto}],
            system=SYSTEM_PROMPT,
            max_tokens=400,
            temperature=0.2,
        )
    except Exception as exc:
        log.warning("sugestao_prazo_llm_falhou", error=str(exc))
        return {"ok": False, "detail": f"Falha ao consultar o modelo: {exc}"[:300]}

    sugestao = parse_sugestao(conteudo)
    if sugestao is None:
        return {"ok": False, "detail": "Resposta do modelo em formato inesperado."}
    return {"ok": True, **sugestao}
