from sqlalchemy import String, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID
import uuid
from datetime import datetime
from app.db.base import Base


class GovRegistryLookup(Base):
    """Fase 217 — auditoria de consulta de CPF/CNPJ contra registro
    governamental (SERPRO). `documento_consultado` é criptografado com o
    mesmo mecanismo de `Client.cpf`/`cnpj` (`core/crypto.py`).
    `resultado_resumo` guarda só nome/razão social + situação cadastral,
    nunca o payload bruto da consulta. `client_id` é nullable porque a
    validação acontece no blur do campo, antes do cliente existir de fato
    no banco."""
    __tablename__ = "gov_registry_lookups"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"))
    tipo_consulta: Mapped[str] = mapped_column(String(10), nullable=False)  # CPF, CNPJ
    documento_consultado: Mapped[str] = mapped_column(String(255), nullable=False)
    resultado_resumo: Mapped[str | None] = mapped_column(Text)
    consultado_por: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
