"""Tese jurídica (Fase 138.4) — lista controlada por escritório, usada pra
classificar processos e agrupar a taxa de êxito (`GET /system/analytics/gestao`).

Ao contrário de `Tribunal` (referência global, seedada do CNJ), tese é
vocabulário específico de cada tenant — cada escritório tem seu próprio
conjunto de teses recorrentes ("prescrição intercorrente", "dano moral in
re ipsa" etc.), escolhido manualmente por um humano ao criar/editar um
processo, não sugerido por IA (decisão tomada com o usuário — ver plano)."""
from sqlalchemy import String, Boolean, ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID
import uuid
from datetime import datetime

from app.db.base import Base


class Tese(Base):
    __tablename__ = "teses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "nome", name="uq_tese_tenant_nome"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    area_direito: Mapped[str | None] = mapped_column(String(100))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
