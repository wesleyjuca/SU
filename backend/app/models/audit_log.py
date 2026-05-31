from sqlalchemy import String, Boolean, ForeignKey, Text, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime
from app.db.base import Base


class AuditLog(Base):
    """
    Registro imutável de auditoria. O trigger PostgreSQL proíbe UPDATE e DELETE.
    Toda ação do sistema deve ser registrada aqui para conformidade com LGPD.
    """
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))   # NULL = evento de sistema
    agent_name: Mapped[str | None] = mapped_column(String(100))
    run_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(100), nullable=False)  # CREATE_PETITION, APPROVE_CONTRACT
    resource_type: Mapped[str | None] = mapped_column(String(50))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    old_value: Mapped[dict | None] = mapped_column(JSONB)
    new_value: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    session_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_detail: Mapped[str | None] = mapped_column(Text)
    contains_pii: Mapped[bool] = mapped_column(Boolean, default=False)
    legal_basis: Mapped[str | None] = mapped_column(String(100))  # consent, legitimate_interest, contract
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)


class LGPDConsentRecord(Base):
    __tablename__ = "lgpd_consent_records"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id"))
    tipo_dado: Mapped[str | None] = mapped_column(String(100))  # dados_pessoais, comunicacoes_marketing
    consentimento: Mapped[bool] = mapped_column(Boolean, nullable=False)
    base_legal: Mapped[str | None] = mapped_column(String(100))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    texto_versao: Mapped[str | None] = mapped_column(String(20))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
