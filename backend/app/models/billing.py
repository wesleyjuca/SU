"""Cobrança do SaaS por escritório (tenant).

Diferente de `financial.py` (FinancialEntry/BillingInvoice = financeiro do
escritório para OS CLIENTES DELE), aqui é a mensalidade que a PLATAFORMA cobra
de cada escritório-cliente. Gerido pelo SUPERADMIN (billing manual).
"""
from sqlalchemy import String, ForeignKey, Text, Numeric, Date, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime, date
from decimal import Decimal
from app.db.base import Base


class BillingAccount(Base):
    """Conta de cobrança do escritório (1 por tenant).

    status: ATIVO (em dia) · INADIMPLENTE (vencido, só aviso) ·
            SUSPENSO (bloqueio suave de escrita) · ISENTO (raiz/trial).
    """
    __tablename__ = "billing_accounts"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    valor_mensal: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    dia_vencimento: Mapped[int] = mapped_column(Integer, default=10)  # dia do mês (1-28)
    status: Mapped[str] = mapped_column(String(20), default="ATIVO")
    proximo_vencimento: Mapped[date | None] = mapped_column(Date, nullable=True)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TenantPayment(Base):
    """Histórico de pagamentos manuais registrados pelo SUPERADMIN."""
    __tablename__ = "tenant_payments"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    valor: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    competencia: Mapped[str] = mapped_column(String(7), nullable=False)  # "YYYY-MM"
    pago_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    metodo: Mapped[str] = mapped_column(String(30), default="MANUAL")
    registrado_por: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
