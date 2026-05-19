from sqlalchemy import String, Boolean, Integer, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime
from app.db.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    subdomain: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    plan: Mapped[str] = mapped_column(String(50), default="STANDARD")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_users: Mapped[int] = mapped_column(Integer, default=10)
    max_storage_gb: Mapped[int] = mapped_column(Integer, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    config: Mapped["TenantConfig | None"] = relationship(back_populates="tenant", uselist=False)


class TenantConfig(Base):
    __tablename__ = "tenant_configs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Branding
    primary_color: Mapped[str] = mapped_column(String(20), default="#C9A84C")
    secondary_color: Mapped[str] = mapped_column(String(20), default="#1A1A1A")
    accent_color: Mapped[str] = mapped_column(String(20), default="#F5F0E8")
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_dark_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    favicon_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_name: Mapped[str] = mapped_column(String(255), default="AFJ CORE")

    # Layout
    nav_config: Mapped[list | None] = mapped_column(JSONB, default=list)
    dashboard_widgets: Mapped[list | None] = mapped_column(JSONB, default=list)

    # Módulos
    modules_enabled: Mapped[dict | None] = mapped_column(
        JSONB,
        default=lambda: {
            "processos": True,
            "peticoes": True,
            "clientes": True,
            "financeiro": True,
            "agentes": True,
            "visual_law": True,
        },
    )

    document_templates: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    custom_css: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant: Mapped["Tenant"] = relationship(back_populates="config")
