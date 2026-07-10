"""Programa de Integridade — aceite do Código de Conduta e Canal de Denúncias."""
from sqlalchemy import String, Boolean, ForeignKey, Text, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime
from app.db.base import Base


class ConductAcceptance(Base):
    """Aceite registrado do Código de Conduta (por versão do documento)."""
    __tablename__ = "conduct_acceptances"
    __table_args__ = (UniqueConstraint("user_id", "version", name="uq_conduct_user_version"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntegrityReport(Base):
    """Relato do Canal de Denúncias (com opção de anonimato).

    Se `anonimo=True`, `created_by` fica NULO — o anonimato é garantido no
    registro (não apenas na exibição)."""
    __tablename__ = "integrity_reports"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    categoria: Mapped[str] = mapped_column(String(40), nullable=False)  # ETICA, CONFLITO_INTERESSES, DADOS_LGPD, USO_DE_IA, ASSEDIO, OUTROS
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    anonimo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ABERTO", index=True)  # ABERTO, EM_ANALISE, RESOLVIDO
    resolucao: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
