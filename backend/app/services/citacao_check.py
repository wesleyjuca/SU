"""Extração e verificação de citações de legislação e processo (Fases 93/126).

Verificação sob demanda (não bloqueia geração/aprovação de peças): extrai
referências de lei e de número de processo (CNJ) do texto e confere cada
uma contra a fonte oficial (LexML / DataJud). Fail-soft por citação: erro
individual vira "nao_verificavel", nunca derruba as demais.

Súmulas (STF/STJ/TST/TNU) ficam de fora — nenhum dos 4 tribunais expõe API
JSON estável/gratuita pra busca por número (só páginas HTML de busca);
scraping seria frágil demais pra uma verificação de citação jurídica.
"""
from __future__ import annotations

import re

import structlog

log = structlog.get_logger()

_PADRAO_LEI = re.compile(
    r"Lei\s+(?:Complementar\s+)?(?:n[º°\.]*\s*)?(\d{1,3}(?:\.\d{3})*)\s*[/,]\s*(\d{4})",
    re.IGNORECASE,
)

_PADRAO_PROCESSO = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")


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


def extrair_referencias_processo(texto: str) -> list[str]:
    """Extrai números de processo em formato CNJ do texto, deduplicados,
    na ordem de primeira ocorrência."""
    vistas: set[str] = set()
    out: list[str] = []
    for ref in _PADRAO_PROCESSO.findall(texto or ""):
        if ref not in vistas:
            vistas.add(ref)
            out.append(ref)
    return out


async def _verificar_leis(referencias: list[str]) -> list[dict]:
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
            "tipo": "LEI",
            "status": status,
            "titulo": resultado.get("titulo") if resultado else None,
        })
    return out


async def _verificar_processos(referencias: list[str], tribunal: str | None) -> list[dict]:
    out: list[dict] = []
    if not referencias:
        return out

    if not tribunal:
        # Sem tribunal não dá pra verificar: `DataJudFonte` cai num fallback
        # silencioso pra TJCE quando tribunal=None, o que verificaria no
        # tribunal errado e daria um resultado enganoso — melhor não tentar.
        return [
            {"referencia": ref, "tipo": "PROCESSO", "status": "nao_verificavel", "titulo": None}
            for ref in referencias
        ]

    from app.integrations.fontes.registry import obter_fonte

    fonte = obter_fonte("datajud")
    for ref in referencias:
        dados = None
        if fonte:
            try:
                dados = await fonte.detalhar(ref, tribunal)
            except Exception as exc:
                log.warning("verificar_citacao_processo_falhou", ref=ref, error=str(exc))
                dados = None

        # `fetch_processo` devolve None tanto pra "não encontrado" quanto
        # pra falha de rede/timeout — não dá pra distinguir os 2 casos aqui,
        # diferente da verificação de LEI. Por isso só há 2 status possíveis.
        status = "confirmada" if dados else "nao_verificavel"
        out.append({
            "referencia": ref,
            "tipo": "PROCESSO",
            "status": status,
            "titulo": dados.get("classe") if dados else None,
        })
    return out


async def verificar_citacoes(texto: str, tribunal: str | None = None) -> list[dict]:
    """Extrai referências de lei e de processo do texto e confere cada uma
    na fonte oficial correspondente (LexML / DataJud)."""
    refs_lei = extrair_referencias_lei(texto)
    refs_processo = extrair_referencias_processo(texto)
    if not refs_lei and not refs_processo:
        return []

    leis = await _verificar_leis(refs_lei) if refs_lei else []
    processos = await _verificar_processos(refs_processo, tribunal)
    return leis + processos
