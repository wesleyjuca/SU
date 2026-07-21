from abc import ABC, abstractmethod
from typing import ClassVar
import time
import structlog

from app.agents.brain.context import AgentContext
from app.agents.base.result import AgentResult, AgentStatus

log = structlog.get_logger()


class AgentBudgetExceeded(Exception):
    """Custo do run (ou teto mensal do usuário) estourado — a chamada de IA é
    recusada ANTES de ir ao provedor. Sem retry (gastar de novo não resolve)."""


class BaseAgent(ABC):
    """
    Classe base para todos os 19 agentes do AFJ CORE SYSTEM.

    Fornece (Fase 71 — fundação transversal):
    - `ask_llm()`: chamada de IA padronizada com system prompt jurídico
      herdado, few-shot, contabilização automática de tokens/custo e
      GUARDRAIL DE CUSTO (cap por run + teto mensal do usuário).
    - `validate()`: hook de validação da saída, chamado após execute().
    - HITL por criticidade: `criticality="HIGH"` implica aprovação humana.
    - RAG (recall/remember) com degradação graciosa sem Qdrant.
    - Logging estruturado + audit + retry.

    Persistência do run: o registro AgentRun é criado pela API no trigger e
    ATUALIZADO pelo worker ao final (app/workers/tasks/agent_tasks.py) — o
    antigo save_run_to_db daqui era código morto (dupla escrita) e foi
    aposentado nesta fase.
    """
    name: ClassVar[str]
    description: ClassVar[str]
    version: ClassVar[str] = "1.0.0"
    # HITL: criticidade da ação do agente. HIGH = a saída dispara ação externa
    # crítica (protocolar, assinar, enviar) → SEMPRE passa por aprovação humana,
    # mesmo que o autor da subclasse esqueça requires_human_approval.
    criticality: ClassVar[str] = "LOW"          # LOW | MEDIUM | HIGH
    requires_human_approval: ClassVar[bool] = False
    # Validação: se True, saída com problemas vira PARTIAL (senão só registra).
    strict_validation: ClassVar[bool] = False
    # Guardrail de custo: teto de gasto de IA acumulado num único run.
    max_cost_usd_per_run: ClassVar[float] = 1.0
    max_retries: ClassVar[int] = 2

    def __init__(self, db=None, redis=None, qdrant=None):
        self.db = db
        self.redis = redis
        self.qdrant = qdrant

    @abstractmethod
    async def execute(self, ctx: AgentContext) -> AgentResult:
        """Lógica principal do agente. Deve ser implementada por cada agente especializado."""
        ...

    # ─── Chamada de IA padronizada (guardrail de custo + prompt base) ─────────
    @staticmethod
    def build_messages(user_prompt: str, few_shot: list[tuple[str, str]] | None = None) -> list[dict]:
        """Monta a lista de messages com exemplos few-shot opcionais.

        few_shot = [(entrada_exemplo, saida_exemplo), ...] — pares user/assistant
        antes da entrada real, para ancorar formato e tom da resposta."""
        messages: list[dict] = []
        for exemplo_in, exemplo_out in (few_shot or []):
            messages.append({"role": "user", "content": exemplo_in})
            messages.append({"role": "assistant", "content": exemplo_out})
        messages.append({"role": "user", "content": user_prompt})
        return messages

    async def ask_llm(
        self,
        ctx: AgentContext,
        prompt: str | None = None,
        *,
        messages: list[dict] | None = None,
        extra_system: str = "",
        few_shot: list[tuple[str, str]] | None = None,
        model: str | None = None,
        max_tokens: int = 8096,
        temperature: float = 0.3,
    ) -> str:
        """Chamada de IA com o AFJ_LEGAL_SYSTEM_PROMPT herdado por padrão.

        Antes de chamar o provedor:
        1. cap por run — ctx.total_cost_usd ≥ max_cost_usd_per_run → recusa;
        2. teto mensal do usuário (Custos de IA) — over_limit → recusa.
        Depois: contabiliza tokens/custo no ctx automaticamente (o boilerplate
        que cada agente repetia). Retorna só o texto."""
        # 1. Cap por run — protege contra loops/cadeias que estourariam custo
        if ctx.total_cost_usd >= self.max_cost_usd_per_run:
            raise AgentBudgetExceeded(
                f"Cap de custo do run atingido (US$ {ctx.total_cost_usd:.2f} ≥ "
                f"US$ {self.max_cost_usd_per_run:.2f}) — chamada de IA recusada."
            )
        # 2. Teto mensal do usuário (best-effort; sem db ou sem limite → segue)
        if self.db is not None and ctx.triggered_by is not None:
            try:
                from app.services.ai_budget import get_budget_status
                status = await get_budget_status(self.db, ctx.triggered_by, ctx.tenant_id)
                if status and status.get("over_limit"):
                    raise AgentBudgetExceeded(
                        f"Teto mensal de IA do usuário atingido (US$ {status['spent_usd']:.2f} "
                        f"de US$ {status['limit_usd']:.2f})."
                    )
            except AgentBudgetExceeded:
                raise
            except Exception as exc:
                log.warning("agent_budget_check_failed", agent=self.name, error=str(exc))

        from app.integrations.anthropic_client import call_claude, AFJ_LEGAL_SYSTEM_PROMPT
        system = AFJ_LEGAL_SYSTEM_PROMPT + (("\n\n" + extra_system) if extra_system else "")
        msgs = messages if messages is not None else self.build_messages(prompt or "", few_shot)

        content, tokens_in, tokens_out, cost = await call_claude(
            messages=msgs, system=system, model=model,
            max_tokens=max_tokens, temperature=temperature,
        )
        ctx.add_tokens(tokens_in + tokens_out, cost)
        log.info("agent_llm_call", agent=self.name, tokens=tokens_in + tokens_out,
                 cost_usd=round(cost, 4), run_total_usd=round(ctx.total_cost_usd, 4))
        return content

    # ─── Validação de saída (hook) ────────────────────────────────────────────
    async def validate(self, ctx: AgentContext, result: AgentResult) -> list[str]:
        """Valida a saída do agente; retorna a lista de problemas encontrados.

        Subclasses devem sobrescrever com checagens específicas (ex.: sintaxe
        Mermaid no visual_law, conformidade OAB no marketing). A base checa o
        contrato mínimo do resultado."""
        issues: list[str] = []
        if result.status == AgentStatus.SUCCESS and not result.output and not result.artifacts:
            issues.append("SUCCESS sem output nem artifacts — resultado vazio")
        if result.status == AgentStatus.FAILED and not result.error:
            issues.append("FAILED sem mensagem de erro")
        return issues

    async def run(self, ctx: AgentContext) -> AgentResult:
        """
        Wrapper de execução. Gerencia: logging, timing, erros, custo,
        validação e approval gate. Não sobrescreva — implemente execute().
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

                # Validação de saída (hook) — nunca derruba o run por si só
                try:
                    issues = await self.validate(ctx, result)
                except Exception as exc:
                    issues = []
                    log.warning("agent_validate_crashed", agent=self.name, error=str(exc))
                if issues:
                    result.metadata["validation_issues"] = issues
                    log.warning("agent_validation_issues", agent=self.name, issues=issues)
                    ctx.add_audit_event("AGENT_VALIDATION", {"issues": issues})
                    if self.strict_validation and result.status == AgentStatus.SUCCESS:
                        result.status = AgentStatus.PARTIAL

                # HITL: flag explícito OU criticidade alta exigem humano
                exige_humano = self.requires_human_approval or self.criticality == "HIGH"
                if exige_humano and ctx.approved is None:
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

            except AgentBudgetExceeded as exc:
                # Custo estourado: retry gastaria de novo — falha direto.
                last_error = exc
                log.warning("agent_budget_exceeded", agent=self.name, error=str(exc))
                break
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
        """Consulta a memória institucional via RAG (sem Qdrant → [])."""
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
