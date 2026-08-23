from sqlalchemy import String, Text, ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID
import uuid
from datetime import datetime
from app.db.base import Base


class AgentAreaPlaybook(Base):
    """Fase 216 — orientação/checklist editável por área do direito,
    injetada no prompt do `strategy_agent` (único consumidor por
    enquanto — o campo é sobre a ÁREA, não sobre o agente, por isso não
    tem `agent_name`). Escrita restrita a ADMIN/SOCIO/GESTOR."""
    __tablename__ = "agent_area_playbooks"
    __table_args__ = (UniqueConstraint("tenant_id", "area_direito", name="uq_agent_playbook_tenant_area"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    area_direito: Mapped[str] = mapped_column(String(100), nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    atualizado_por: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
