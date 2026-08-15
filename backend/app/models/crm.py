"""CRM — funil de vendas (oportunidades/negócios)."""
from sqlalchemy import String, ForeignKey, Text, Numeric, Integer, Date
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime, date
from decimal import Decimal
from app.db.base import Base


class Opportunity(Base):
    """Oportunidade de negócio no funil de vendas do escritório."""
    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id"))  # lead pode não ser cliente ainda
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    valor_estimado: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), default=0)
    # LEAD, QUALIFICACAO, PROPOSTA, NEGOCIACAO, GANHO, PERDIDO
    estagio: Mapped[str] = mapped_column(String(20), default="LEAD", index=True)
    probabilidade: Mapped[int] = mapped_column(Integer, default=50)  # 0-100
    origem: Mapped[str | None] = mapped_column(String(100))
    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    expected_close: Mapped[date | None] = mapped_column(Date)
    motivo_perda: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
