from enum import Enum
from dataclasses import dataclass, field


class AgentStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    PARTIAL = "PARTIAL"
    SKIPPED = "SKIPPED"


@dataclass
class AgentResult:
    status: AgentStatus
    agent_name: str
    output: dict = field(default_factory=dict)
    artifacts: list[dict] = field(default_factory=list)  # documentos gerados, relatórios
    next_agents: list[str] = field(default_factory=list) # encadeamento de agentes
    error: str | None = None
    approval_required: dict | None = None   # descrição do que precisa de aprovação
    tokens_used: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    metadata: dict = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status == AgentStatus.SUCCESS

    @property
    def needs_approval(self) -> bool:
        return self.status == AgentStatus.AWAITING_APPROVAL

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "agent_name": self.agent_name,
            "output": self.output,
            "artifacts": self.artifacts,
            "next_agents": self.next_agents,
            "error": self.error,
            "approval_required": self.approval_required,
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }
