"""Circuit breaker real para as fontes processuais (Fase 73).

Implementa os três estados clássicos de um disjuntor (abertura temporizada):

    closed  → tudo passa; conta falhas consecutivas
    open    → nada passa; após `reset_timeout` s vira half_open
    half_open → deixa passar UMA tentativa; sucesso fecha, falha reabre

Sem dependências externas e seguro em asyncio (o estado é manipulado de forma
síncrona; `run()` só aguarda a factory do chamador). Tudo é fail-soft: `run()`
nunca propaga exceção — devolve `default` e contabiliza a falha.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, TypeVar

import structlog

log = structlog.get_logger()

T = TypeVar("T")

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 3,
        reset_timeout: float = 1800.0,
        *,
        name: str = "",
    ) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self.reset_timeout = max(0.0, reset_timeout)
        self.name = name
        self._failures = 0
        self._opened_at: datetime | None = None
        self._state = CLOSED

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @property
    def state(self) -> str:
        """Estado atual, aplicando a transição preguiçosa open→half_open."""
        if self._state == OPEN and self._opened_at is not None:
            if self._now() - self._opened_at >= timedelta(seconds=self.reset_timeout):
                self._state = HALF_OPEN
        return self._state

    def allow(self) -> bool:
        """True se uma chamada pode passar agora (fechado ou half_open)."""
        return self.state != OPEN

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._state = CLOSED

    def record_failure(self) -> None:
        self._failures += 1
        # Falha em half_open reabre imediatamente; em closed abre no limiar.
        if self._state == HALF_OPEN or self._failures >= self.failure_threshold:
            self._state = OPEN
            self._opened_at = self._now()
            log.warning("circuit_open", fonte=self.name, failures=self._failures)

    async def run(self, factory: Callable[[], Awaitable[T]], *, default: Any = None) -> Any:
        """Executa `factory()` sob o breaker.

        - Circuito aberto → retorna `default` sem chamar.
        - Exceção da factory → registra falha e retorna `default` (fail-soft).
        - Sucesso → registra sucesso e retorna o resultado.
        """
        if not self.allow():
            log.debug("circuit_skip", fonte=self.name)
            return default
        try:
            resultado = await factory()
        except Exception as exc:  # fail-soft: nunca propaga
            self.record_failure()
            log.warning("circuit_call_failed", fonte=self.name, error=str(exc))
            return default
        self.record_success()
        return resultado
