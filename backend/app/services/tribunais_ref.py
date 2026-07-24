"""Referência canônica de tribunais (Fase 74) — helpers puros + semeadura.

Deriva tipo/UF do código e normaliza o código do DF. `linhas_seed()` gera as
linhas da tabela `tribunais` a partir de `TRIBUNAL_INDICES` (o mapa mais
completo, em `integrations/tribunais/cnj.py`). Tudo síncrono e sem I/O —
testável isoladamente; a gravação idempotente é feita em `core/events.py`.
"""
from __future__ import annotations

import re

from app.integrations.tribunais.cnj import TRIBUNAL_INDICES

# Código canônico do DF = TJDFT (índice DataJud api_publica_tjdft). Havia
# inconsistência TJDF (cnj.py) vs TJDFT (process_agent) — normalizamos p/ TJDFT.
_ALIASES = {"TJDF": "TJDFT"}

_TJ_UF_RE = re.compile(r"^TJ([A-Z]{2})$")


def normalizar_codigo(codigo: str | None) -> str:
    """Uppercase + resolve aliases (TJDF→TJDFT). Retorna '' se vazio."""
    c = (codigo or "").strip().upper()
    return _ALIASES.get(c, c)


def derivar_tipo(codigo: str) -> str:
    if codigo.startswith("TRT"):
        return "TRABALHO"
    if codigo.startswith("TRF"):
        return "FEDERAL"
    if codigo.startswith("TJ"):
        return "ESTADUAL"
    return "SUPERIOR"


def derivar_uf(codigo: str) -> str | None:
    if codigo == "TJDFT":
        return "DF"
    m = _TJ_UF_RE.match(codigo)
    return m.group(1) if m else None


def linhas_seed() -> list[dict]:
    """Linhas p/ a tabela `tribunais`, derivadas do mapa canônico (dedup por
    código normalizado)."""
    linhas: dict[str, dict] = {}
    for codigo_raw, index in TRIBUNAL_INDICES.items():
        codigo = normalizar_codigo(codigo_raw)
        if not codigo:
            continue
        linhas[codigo] = {
            "codigo": codigo,
            "tipo": derivar_tipo(codigo),
            "uf": derivar_uf(codigo),
            "datajud_index": index,
            "ativo": True,
        }
    return list(linhas.values())


# ─── Cache de leitura (Fase 87) — a tabela `tribunais` passa a ser CONSULTADA ──
# Até aqui a tabela só era escrita (seed); nada no runtime a lia. `_index` do
# CNJDataJudClient é uma property síncrona chamada de dentro de métodos
# assíncronos — não dá pra trocar por uma query direta sem tornar a property
# assíncrona (invasivo). Solução: cache em memória, carregado 1x no boot a
# partir do banco (não do dict hardcoded); `TRIBUNAL_INDICES` vira só o
# fallback de degradação (ambiente sem DB), preservando o comportamento atual.
_CACHE: dict[str, str] | None = None


async def carregar_cache(db) -> dict[str, str]:
    """Popula o cache módulo a partir da tabela `tribunais` (só ativos).
    Best-effort: falha não derruba o boot, o cache simplesmente fica vazio e
    `indice_datajud` devolve None (chamador cai no fallback hardcoded)."""
    global _CACHE
    try:
        from sqlalchemy import select
        from app.models.tribunal import Tribunal
        rows = (await db.execute(
            select(Tribunal.codigo, Tribunal.datajud_index).where(Tribunal.ativo.is_(True))
        )).all()
        _CACHE = {codigo: idx for codigo, idx in rows if idx}
    except Exception:
        _CACHE = _CACHE or {}
    return _CACHE


def indice_datajud(codigo: str) -> str | None:
    """Índice DataJud do tribunal, lido do cache (tabela). None se o cache
    ainda não foi carregado ou não tem o código — o chamador cai no fallback
    hardcoded (TRIBUNAL_INDICES), idêntico ao comportamento de antes da Fase 87."""
    if not _CACHE:
        return None
    return _CACHE.get(normalizar_codigo(codigo))
