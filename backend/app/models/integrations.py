"""Integrações externas por usuário — Google Workspace (tokens cifrados)."""
from sqlalchemy import String, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID
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
