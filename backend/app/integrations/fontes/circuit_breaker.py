"""Circuit breaker real para as fontes processuais (Fase 73).

Implementa os três estados clássicos de um disjuntor (abertura temporizada):

    closed  → tudo passa; conta falhas consecutivas
    open    → nada passa; após `reset_timeout` s vira half_open
    half_open → deixa passar UMA tentativa; sucesso fecha, falha reabre

Sem dependências externas e seguro em asyncio (o estado é manipulado de forma
síncrona; `run()` só aguarda a factory do chamador). Tudo é fail-soft: `run()`
nunca propaga exceção — devolve `default` e contabiliza a falha.

Fase 166 — antes o estado (`_failures`/`_state`/`_opened_at`) vivia só em
memória do processo Python que criou a instância. Como o web (uvicorn) e o
worker (Celery) são processos SEPARADOS, cada um tinha sua própria cópia
isolada — o painel Cérebro (que roda no processo web) nunca via as falhas
que a captura de verdade (que roda no worker, via polling/Beat) registrava,
então o indicador "Fontes da Captura" ficava sempre "ok" independente da
saúde real. `run()` agora espelha o estado no Redis (best-effort, nunca
bloqueia por falta/falha de infra opcional — mesmo espírito de `TaskLock`)
e hidrata a partir dele na primeira chamada de cada instância — cobre tanto
as fontes públicas de vida longa (`comunica`/`datajud`, 1 instância por
processo) quanto as credenciadas (pdpj/escavador/judit/jusbrasil, uma
instância NOVA por chamada via `para_tenant()` — sem isso, o contador de
falhas consecutivas nunca sobrevivia entre 2 capturas, mesmo dentro do
MESMO processo). `estado_atual()` é o ponto de leitura pro painel — sempre
busca o valor mais fresco do Redis, sem cache, já que é chamado com pouca
frequência (visualização manual + o probe periódico de infra, Fase 164).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, TypeVar

import structlog

log = structlog.get_logger()

T = TypeVar("T")

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"

_REDIS_TTL_SECONDS = 6 * 3600  # folga generosa acima de qualquer reset_timeout real


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
        self._hidratado = False

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @property
    def state(self) -> str:
        """Estado atual (local a este processo), aplicando a transição
        preguiçosa open→half_open. Pra visão compartilhada entre processos,
        ver `estado_atual()`."""
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

    def _redis_key(self) -> str:
        return f"circuit_breaker:{self.name}"

    def _snapshot(self) -> dict:
        return {
            "state": self._state,
            "failures": self._failures,
            "opened_at": self._opened_at.isoformat() if self._opened_at else None,
        }

    async def _persistir(self) -> None:
        """Espelha o estado local no Redis — best-effort, nunca lança."""
        if not self.name:
            return
        try:
            from app.db.redis import get_redis
            redis = await get_redis()
            if not redis:
                return
            await redis.set(self._redis_key(), json.dumps(self._snapshot()), ex=_REDIS_TTL_SECONDS)
        except Exception as exc:
            log.warning("circuit_breaker_persistencia_falhou", fonte=self.name, error=str(exc))

    async def _ler_redis(self) -> dict | None:
        if not self.name:
            return None
        try:
            from app.db.redis import get_redis
            redis = await get_redis()
            if not redis:
                return None
            raw = await redis.get(self._redis_key())
            if not raw:
                return None
            return json.loads(raw)
        except Exception as exc:
            log.warning("circuit_breaker_leitura_falhou", fonte=self.name, error=str(exc))
            return None

    def _aplicar_snapshot(self, dados: dict) -> None:
        self._failures = dados.get("failures", self._failures)
        self._state = dados.get("state", self._state)
        opened_at_raw = dados.get("opened_at")
        self._opened_at = datetime.fromisoformat(opened_at_raw) if opened_at_raw else None

    async def _hidratar(self) -> None:
        """Carrega o estado mais recente do Redis na 1ª chamada desta
        instância — outro processo pode ter registrado falhas que este nunca
        viu. Só roda 1x por instância (custo de I/O evitado no caminho
        quente de chamadas repetidas do MESMO processo)."""
        if self._hidratado:
            return
        self._hidratado = True
        dados = await self._ler_redis()
        if dados:
            self._aplicar_snapshot(dados)

    async def estado_atual(self) -> str:
        """Estado mais fresco possível, incluindo o que outros processos
        gravaram — usado pelo painel Cérebro (Fase 166). Sempre busca no
        Redis (sem cache local), já que é chamado com baixa frequência
        (visualização manual + probe periódico de infra a cada 5min)."""
        dados = await self._ler_redis()
        if dados:
            self._aplicar_snapshot(dados)
        return self.state

    async def run(self, factory: Callable[[], Awaitable[T]], *, default: Any = None) -> Any:
        """Executa `factory()` sob o breaker.

        - Circuito aberto → retorna `default` sem chamar.
        - Exceção da factory → registra falha e retorna `default` (fail-soft).
        - Sucesso → registra sucesso e retorna o resultado.
        """
        await self._hidratar()
        if not self.allow():
            log.debug("circuit_skip", fonte=self.name)
            return default
        try:
            resultado = await factory()
        except Exception as exc:  # fail-soft: nunca propaga
            self.record_failure()
            await self._persistir()
            log.warning("circuit_call_failed", fonte=self.name, error=str(exc))
            return default
        self.record_success()
        await self._persistir()
        return resultado
