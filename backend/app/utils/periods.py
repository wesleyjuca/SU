"""Utilitários de período — centraliza cálculos de data hoje duplicados inline."""
from datetime import datetime, timezone, timedelta


def inicio_mes(now: datetime | None = None) -> datetime:
    """Primeiro instante do mês corrente (UTC)."""
    now = now or datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def range_meses(n: int, now: datetime | None = None) -> datetime:
    """Início da janela dos últimos `n` meses (aprox. 31 dias/mês, como o resto do app)."""
    now = now or datetime.now(timezone.utc)
    return now - timedelta(days=n * 31)
