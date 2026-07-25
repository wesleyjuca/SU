"""Extração e verificação de citações de legislação (Fase 93).

Fatia inicial da verificação de citações: só leis (não súmulas/processos
ainda — ficam pra fase futura). Sob demanda (não bloqueia geração/aprovação
de peças) — extrai referências de lei do texto e confere cada uma contra o
LexML (fonte oficial). Fail-soft por citação: erro individual vira
"nao_verificavel", nunca derruba as demais.
"""
from __future__ import annotations

import re

import structlog

log = structlog.get_logger()

_PADRAO_LEI = re.compile(
    r"Lei\s+(?:Complementar\s+)?(?:n[º°\.]*\s*)?(\d{1,3}(?:\.\d{3})*)\s*[/,]\s*(\d{4})",
    re.IGNORECASE,
)


def extrair_referencias_lei(texto: str) -> list[str]:
    """Extrai referências de lei do texto (ex.: "Lei nº 8.078/1990" → "8078/1990"),
    deduplicadas, na ordem de primeira ocorrência."""
    vistas: set[str] = set()
    out: list[str] = []
    for numero, ano in _PADRAO_LEI.findall(texto or ""):
        ref = f"{numero.replace('.', '')}/{ano}"
        if ref not in vistas:
            vistas.add(ref)
            out.append(ref)
    return out


async def verificar_citacoes(texto: str) -> list[dict]:
    """Extrai referências de lei do texto e confere cada uma no LexML."""
    referencias = extrair_referencias_lei(texto)
    if not referencias:
        return []

    from app.integrations.lexml.client import buscar_lei

    out: list[dict] = []
    for ref in referencias:
        try:
            resultado = await buscar_lei(ref)
        except Exception as exc:
            log.warning("verificar_citacao_falhou", ref=ref, error=str(exc))
            resultado = None

        if resultado is None:
            status = "nao_verificavel"
        elif resultado.get("encontrado"):
            status = "confirmada"
        else:
            status = "nao_encontrada"

        out.append({
            "referencia": ref,
            "status": status,
            "titulo": resultado.get("titulo") if resultado else None,
        })
    return out
