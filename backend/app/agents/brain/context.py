from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


@dataclass
class AgentContext:
    """
    Objeto de contexto compartilhado que flui por toda a cadeia de agentes.
    Cada agente lê e enriquece este contexto — nunca o substitui completamente.
    """
    # ─── Identidade da execução ───────────────────────────────────────────────
    run_id: uuid.UUID = field(default_factory=uuid.uuid4)
    session_id: uuid.UUID = field(default_factory=uuid.uuid4)
    triggered_by: uuid.UUID | None = None      # user_id ou None para eventos de sistema

    # ─── Especificação da tarefa ──────────────────────────────────────────────
    task_type: str = ""                        # generate_petition, monitor_process, etc.
    task_input: dict = field(default_factory=dict)
    priority: str = "NORMAL"                  # LOW, NORMAL, HIGH, URGENT

    # ─── Contexto jurídico ────────────────────────────────────────────────────
    process_id: uuid.UUID | None = None
    client_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None

    # ─── Estado acumulado (cada agente pode escrever aqui) ────────────────────
    state: dict = field(default_factory=dict)

    # ─── Memória recuperada via RAG ───────────────────────────────────────────
    retrieved_memory: list[dict] = field(default_factory=list)

    # ─── Rastreio da cadeia de agentes ────────────────────────────────────────
    agents_invoked: list[str] = field(default_factory=list)
    current_agent: str = ""

    # ─── Controle de aprovação humana ────────────────────────────────────────
    requires_approval: bool = False
    approval_id: uuid.UUID | None = None
    approved: bool | None = None               # None=pendente, True=aprovado, False=rejeitado
    rejection_reason: str | None = None

    # ─── Eventos de auditoria acumulados nesta execução ──────────────────────
    audit_events: list[dict] = field(default_factory=list)

    # ─── Rastreio de custo ────────────────────────────────────────────────────
    total_tokens: int = 0
    total_cost_usd: float = 0.0

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_audit_event(self, action: str, details: dict | None = None):
        self.audit_events.append({
            "action": action,
            "agent": self.current_agent,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details or {},
        })

    def add_tokens(self, tokens: int, cost_usd: float = 0.0):
        self.total_tokens += tokens
        self.total_cost_usd += cost_usd

    def set_state(self, key: str, value: Any):
        self.state[key] = value

    def get_state(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def to_dict(self) -> dict:
        return {
            "run_id": str(self.run_id),
            "session_id": str(self.session_id),
            "triggered_by": str(self.triggered_by) if self.triggered_by else None,
            "task_type": self.task_type,
            "task_input": self.task_input,
            "priority": self.priority,
            "process_id": str(self.process_id) if self.process_id else None,
            "client_id": str(self.client_id) if self.client_id else None,
            "document_id": str(self.document_id) if self.document_id else None,
            "state": self.state,
            "agents_invoked": self.agents_invoked,
            "current_agent": self.current_agent,
            "requires_approval": self.requires_approval,
            "approval_id": str(self.approval_id) if self.approval_id else None,
            "approved": self.approved,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
        }
