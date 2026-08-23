"""Custom Agents — Fase 140.2: ADMIN propõe agentes de IA customizados
(prompt-driven, sem código bespoke — ver app/agents/custom/
custom_agent_executor.py) que um SUPERADMIN deve aprovar antes de ficarem
disponíveis plataforma-wide (mesmo catálogo dos 19 agentes nativos,
agent_map em app/agents/brain/orchestrator.py). Tabela plataforma-wide —
tenant_id é AUDITORIA de quem propôs, não escopo de visibilidade/execução
(mesma decisão da Fase 140.1 para agent_prompt_configs).

Fase 193 — edição de um agente já APROVADO agora é possível (débito
técnico documentado desde a 140.2), seguindo o padrão apontado aqui desde
então: `CustomAgentVersion` snapshota o estado ANTERIOR a cada edição,
mesmo padrão de `AgentPromptVersion` (app/models/agent_prompt.py)."""
from sqlalchemy import String, ForeignKey, Text, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime
from app.db.base import Base


class CustomAgent(Base):
    """Definição de um agente customizado: name + description + system_prompt
    + rag_collections opcional. Execução = 1 retrieve() (se rag_collections)
    + 1 call_claude() — nunca um BaseAgent subclass novo por proposta."""
    __tablename__ = "custom_agents"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # None/[] = sem RAG, o executor pula o retrieve() e chama call_claude() direto.
    rag_collections: Mapped[list[str] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDENTE", index=True)  # PENDENTE|APROVADO|REJEITADO
    # Teto de custo por execução — quem CONTROLA é o SUPERADMIN no /resolve
    # (não o proponente no POST), evita um ADMIN se auto-conceder orçamento
    # alto que o aprovador aceita sem notar.
    max_cost_usd_per_run: Mapped[float] = mapped_column(Float, nullable=False, default=0.50)
    # Fase 225 — só relevante quando o agente é anexado ao final de uma chain
    # multi-agente (router.py::CUSTOM_AGENT_APPENDABLE_CHAINS); no dispatch
    # avulso (run_custom_agent) não muda nada. Reaproveita o mesmo mecanismo
    # de HITL que BaseAgent.run() já checa pros 19 agentes nativos — quem
    # controla é o SUPERADMIN no /resolve ou /PATCH, nunca o proponente.
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Fase 180 — nullable pra permitir exclusão real de usuário (SUPERADMIN):
    # o agente aprovado é plataforma-wide, não pode ser apagado junto do
    # proponente. NULL = "proponente removido", nunca escrito no fluxo normal
    # de criação (o schema/endpoint de criação continua exigindo o autor).
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)  # auditoria — NÃO usado p/ escopo
    approved_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CustomAgentVersion(Base):
    """Snapshot do estado ANTERIOR de um CustomAgent já APROVADO, gravado a
    cada edição (Fase 193) — mesmo padrão de AgentPromptVersion: guarda o
    valor antigo antes de sobrescrever, nunca o novo."""
    __tablename__ = "custom_agent_versions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("custom_agents.id", ondelete="CASCADE"), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    rag_collections: Mapped[list[str] | None] = mapped_column(JSONB)
    max_cost_usd_per_run: Mapped[float] = mapped_column(Float, nullable=False)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    change_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
