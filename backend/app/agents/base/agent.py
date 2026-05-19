from abc import ABC, abstractmethod
from typing import ClassVar
import time
import uuid
import structlog

from app.agents.brain.context import AgentContext
from app.agents.base.result import AgentResult, AgentStatus

log = structlog.get_logger()


class BaseAgent(ABC):
    """
    Classe base para todos os 19 agentes do AFJ CORE SYSTEM.

    Fornece:
    - Logging estruturado + audit
    - Rastreio de custo e tokens
    - Tratamento de erros com retry
    - Interface para RAG (recall/remember)
    - Integração com approval gate
    """
    name: ClassVar[str]
    description: ClassVar[str]
    version: ClassVar[str] = "1.0.0"
    requires_human_approval: ClassVar[bool] = False
    max_retries: ClassVar[int] = 2

    def __init__(self, db=None, redis=None, qdrant=None):
        self.db = db
        self.redis = redis
        self.qdrant = qdrant

    @abstractmethod
    async def execute(self, ctx: AgentContext) -> AgentResult:
        """Lógica principal do agente. Deve ser implementada por cada agente especializado."""
        ...

    async def run(self, ctx: AgentContext) -> AgentResult:
        """
        Wrapper de execução. Gerencia: logging, timing, erros, approval gate.
        Não sobrescreva este método — implemente execute().
        """
        ctx.current_agent = self.name
        ctx.agents_invoked.append(self.name)

        start_ms = int(time.time() * 1000)
        log.info("agent_start", agent=self.name, run_id=str(ctx.run_id), task=ctx.task_type)
        ctx.add_audit_event("AGENT_START", {"agent": self.name, "task": ctx.task_type})

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = await self.execute(ctx)
                result.duration_ms = int(time.time() * 1000) - start_ms

                ctx.add_tokens(result.tokens_used, result.cost_usd)

                if self.requires_human_approval and ctx.approved is None:
                    result.status = AgentStatus.AWAITING_APPROVAL

                log.info(
                    "agent_complete",
                    agent=self.name,
                    status=result.status,
                    tokens=result.tokens_used,
                    duration_ms=result.duration_ms,
                )
                ctx.add_audit_event("AGENT_COMPLETE", {
                    "status": result.status,
                    "tokens": result.tokens_used,
                    "duration_ms": result.duration_ms,
                })
                return result

            except Exception as exc:
                last_error = exc
                log.warning("agent_attempt_failed", agent=self.name, attempt=attempt, error=str(exc))
                if attempt == self.max_retries:
                    break

        ctx.add_audit_event("AGENT_FAILED", {"error": str(last_error)})
        log.error("agent_failed", agent=self.name, error=str(last_error))
        return AgentResult(
            status=AgentStatus.FAILED,
            agent_name=self.name,
            error=str(last_error),
            duration_ms=int(time.time() * 1000) - start_ms,
        )

    async def recall(self, ctx: AgentContext, query: str, collections: list[str] | None = None, k: int = 5) -> list[dict]:
        """Consulta a memória institucional via RAG."""
        if not self.qdrant:
            return []
        try:
            from app.rag.retrieval import retrieve
            results = await retrieve(self.qdrant, query, collections=collections, k=k)
            ctx.retrieved_memory.extend(results)
            return results
        except Exception as exc:
            log.warning("rag_recall_failed", agent=self.name, error=str(exc))
            return []

    async def remember(self, ctx: AgentContext, key: str, value: dict, memory_type: str = "EPISODIC"):
        """Persiste informação na memória do agente."""
        if not self.db:
            return
        try:
            from app.models.agent_run import AgentMemory
            memory = AgentMemory(
                agent_name=self.name,
                memory_type=memory_type,
                key=key,
                value_json=value,
                context_id=ctx.process_id or ctx.client_id,
            )
            self.db.add(memory)
            await self.db.flush()
        except Exception as exc:
            log.warning("remember_failed", agent=self.name, key=key, error=str(exc))

    async def save_run_to_db(self, ctx: AgentContext, result: AgentResult):
        """Persiste o registro de execução no banco."""
        if not self.db:
            return
        try:
            from app.models.agent_run import AgentRun
            run = AgentRun(
                id=ctx.run_id,
                agent_name=self.name,
                session_id=ctx.session_id,
                trigger_type="MANUAL",
                triggered_by=ctx.triggered_by,
                input_data=ctx.task_input,
                output_data=result.output,
                status=result.status.value,
                error_message=result.error,
                tokens_used=result.tokens_used,
                cost_usd=result.cost_usd,
                duration_ms=result.duration_ms,
                requires_approval=result.needs_approval,
            )
            self.db.add(run)
            await self.db.flush()
        except Exception as exc:
            log.error("save_run_failed", agent=self.name, error=str(exc))
