"""Classificação de prioridade por IA de intimações/publicações (Fase 244).

Roda dentro da varredura diária (scan_publicacoes), uma vez por intimação
capturada — antes disso a única sugestão de IA do sistema era sob demanda,
dentro do modal de triagem (prazo_sugestao.py), nunca persistida. Aqui é
só uma classificação de URGÊNCIA (alta/média/baixa) + resumo curto, pra
aparecer JÁ NA LISTAGEM (mesmo padrão que o Astrea usa, citado no
diagnóstico de cadastros) — não substitui a sugestão de tipo/dias de prazo
já existente, que continua só dentro do modal.

Fail-soft: qualquer erro (rede, parsing, formato) retorna None — o
chamador (dje_monitor.py) simplesmente deixa os 3 campos como NULL e a
intimação aparece sem selo de prioridade (comportamento de antes desta
fase), nunca quebra a varredura inteira. Sem `user_ai_creds()` de
propósito — é um job periódico sem usuário específico disparando, mesmo
padrão já usado em jurisprudencia_sync.py::classificar_acordao (chave
central do servidor, não BYOK).
"""
from __future__ import annotations

import json
import re

import structlog

log = structlog.get_logger()

PRIORIDADES_VALIDAS = {"ALTA", "MEDIA", "BAIXA"}
_TRUNCAMENTO = 3000

SYSTEM_PROMPT = """Você é um assistente jurídico que classifica a URGÊNCIA de uma intimação/
publicação do Diário de Justiça, pra ajudar um advogado a priorizar sua fila de triagem.

Responda APENAS com um objeto JSON válido (nada de texto antes ou depois), neste
formato exato:
{"prioridade": "ALTA|MEDIA|BAIXA", "resumo": "..."}

Regras:
- "ALTA": exige providência/resposta com prazo curto ou pena de preclusão/revelia
  (ex.: citação, intimação para contestar/recorrer, decisão que impõe prazo fatal).
- "MEDIA": tem relevância mas sem urgência imediata clara (ex.: decisão interlocutória
  sem prazo explícito, designação de audiência distante).
- "BAIXA": mero expediente, ciência de ato já cumprido, ou sem exigência de providência
  (ex.: juntada de documento, publicação de sentença já favorável sem recurso pendente).
- "resumo": 1 frase curta (até 140 caracteres) resumindo do que se trata, em português.
- Nunca invente prazo nem dê conselho jurídico — só classifique a urgência aparente."""


def _extrair_objeto(texto: str) -> dict | None:
    if not texto:
        return None
    limpo = texto.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", limpo, re.DOTALL)
    candidato = m.group(1) if m else limpo
    if not m:
        i, f = candidato.find("{"), candidato.rfind("}")
        if i == -1 or f == -1 or f < i:
            return None
        candidato = candidato[i:f + 1]
    try:
        dados = json.loads(candidato)
        return dados if isinstance(dados, dict) else None
    except Exception:
        return None


def parse_classificacao(texto: str) -> dict | None:
    dados = _extrair_objeto(texto)
    if dados is None:
        return None
    prioridade = str(dados.get("prioridade") or "").strip().upper()
    if prioridade not in PRIORIDADES_VALIDAS:
        return None
    resumo = str(dados.get("resumo") or "").strip()[:140]
    return {"prioridade": prioridade, "resumo": resumo}


async def classificar_intimacao(texto: str) -> dict | None:
    """Classifica a prioridade de 1 intimação via LLM. Retorna
    {prioridade, resumo} ou None (fail-soft — nunca lança)."""
    from app.integrations.llm_client import call_llm

    trecho = (texto or "")[:_TRUNCAMENTO]
    if not trecho.strip():
        return None
    try:
        conteudo, _in_tok, _out_tok, _custo = await call_llm(
            messages=[{"role": "user", "content": trecho}],
            system=SYSTEM_PROMPT,
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            temperature=0.0,
        )
    except Exception as exc:
        log.warning("intimacao_classificacao_llm_falhou", error=str(exc))
        return None

    resultado = parse_classificacao(conteudo)
    if resultado is None:
        log.warning("intimacao_classificacao_formato_invalido", resposta=conteudo[:200])
        return None
    return resultado
