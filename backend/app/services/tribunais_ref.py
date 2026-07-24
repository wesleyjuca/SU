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
