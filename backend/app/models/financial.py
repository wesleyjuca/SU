from sqlalchemy import String, ForeignKey, Text, Numeric, Date
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime, date
from decimal import Decimal
from app.db.base import Base


class FinancialEntry(Base):
    __tablename__ = "financial_entries"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)  # RECEITA, DESPESA
    categoria: Mapped[str | None] = mapped_column(String(100))     # HONORARIOS, CUSTAS, DESLOCAMENTO
    client_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id"))
    process_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("legal_processes.id"))
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    data_vencimento: Mapped[date | None] = mapped_column(Date)
    data_pagamento: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="PENDENTE")  # PENDENTE, PAGO, CANCELADO
    nf_numero: Mapped[str | None] = mapped_column(String(50))
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BillingInvoice(Base):
    """Fatura de honorários emitida pelo escritório ao seu cliente."""
    __tablename__ = "billing_invoices"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id"))
    process_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("legal_processes.id"))
    numero: Mapped[str | None] = mapped_column(String(50), unique=True)
    descricao: Mapped[str | None] = mapped_column(Text)
    itens: Mapped[list | None] = mapped_column(JSONB)  # [{descricao, valor}]
    periodo_inicio: Mapped[date | None] = mapped_column(Date)
    periodo_fim: Mapped[date | None] = mapped_column(Date)
    data_vencimento: Mapped[date | None] = mapped_column(Date)
    valor_total: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    status: Mapped[str] = mapped_column(String(20), default="RASCUNHO")  # RASCUNHO/EMITIDA/PAGA/CANCELADA
    # Pagamento online (Fase 68): link gerado no gateway conectado do escritório
    payment_link: Mapped[str | None] = mapped_column(Text)
    payment_provider: Mapped[str | None] = mapped_column(String(30))     # stripe | mercadopago
    payment_external_id: Mapped[str | None] = mapped_column(String(150))  # checkout session / preference id
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    emitido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pago_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
