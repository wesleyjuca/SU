"""Integrações externas — Google (por usuário) e hub genérico (por escritório).

Credenciais sempre cifradas em repouso via app.core.crypto."""
from sqlalchemy import String, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime
from app.db.base import Base


class GoogleIntegration(Base):
    """Conexão OAuth do usuário com o Google Workspace.

    Os tokens são cifrados em repouso (app.core.crypto). O refresh_token
    permite renovar o access_token sem novo consentimento."""
    __tablename__ = "google_integrations"
    __table_args__ = (UniqueConstraint("user_id", name="uq_google_integration_user"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    google_email: Mapped[str | None] = mapped_column(String(255))
    access_token_enc: Mapped[str | None] = mapped_column(Text)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TenantIntegration(Base):
    """Conexão do ESCRITÓRIO com um provedor externo (hub de integrações).

    Genérico: `provider` identifica o serviço (stripe, mercadopago, clicksign,
    whatsapp…), `credentials_enc` guarda um JSON cifrado com as credenciais e
    `extra_data` guarda metadados não-sensíveis (conta conectada, último
    webhook, etc.). Uma conexão por (tenant, provider)."""
    __tablename__ = "tenant_integrations"
    __table_args__ = (UniqueConstraint("tenant_id", "provider", name="uq_tenant_integration_provider"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="CONECTADA")  # CONECTADA | ERRO
    credentials_enc: Mapped[str | None] = mapped_column(Text)   # JSON cifrado (Fernet)
    extra_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    connected_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
