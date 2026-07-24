"""Ring buffer em memória dos logs recentes (Fase 82) — painel Logs do Cérebro.

Um structlog processor (registrado em main.py, antes do renderer) faz append de
cada evento a um deque limitado. Nada é persistido — só os últimos N eventos, no
processo. Consumido por GET /system/brain/logs (SUPERADMIN). Best-effort: o
append nunca levanta (não pode derrubar o logging).
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

_MAX = 500
_BUF: "deque[dict]" = deque(maxlen=_MAX)

_NIVEIS = {"debug": 10, "info": 20, "warning": 30, "warn": 30, "error": 40, "critical": 50, "exception": 40}
_META = {"event", "level", "timestamp", "logger"}


def capture_processor(logger, method_name, event_dict):
    """structlog processor: registra o evento no buffer e o repassa intacto."""
    try:
        extra = {k: str(v)[:200] for k, v in event_dict.items() if k not in _META}
        _BUF.append({
            "ts": event_dict.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            "level": (event_dict.get("level") or method_name or "info").lower(),
            "event": str(event_dict.get("event", ""))[:300],
            "extra": extra,
        })
    except Exception:
        pass
    return event_dict


def snapshot(limit: int = 200, level: str | None = None) -> list[dict]:
    """Últimos eventos (mais recentes primeiro), opcionalmente filtrados por nível
    mínimo (ex.: level="warning" traz warning/error/critical)."""
    itens = list(_BUF)
    if level:
        alvo = _NIVEIS.get(level.lower(), 0)
        itens = [e for e in itens if _NIVEIS.get(e["level"], 0) >= alvo]
    return itens[-limit:][::-1]
