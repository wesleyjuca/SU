"""Intimação/publicação capturada do DJe (Comunica/DJEN) — fila de triagem.

Cada intimação vira andamento no processo + notificação; o PRAZO só é criado
após triagem humana (o advogado confirma tipo e dias). Evita prazo calculado
errado — segue o HITL do sistema.
"""
from sqlalchemy import String, Text, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID
import uuid
from datetime import datetime, date
from app.db.base import Base


class Intimacao(Base):
    __tablename__ = "intimacoes"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True)
    # Processo casado por número CNJ (pode não existir ainda no sistema).
    process_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("legal_processes.id", ondelete="SET NULL"))
    oab: Mapped[str | None] = mapped_column(String(30))
    numero_cnj: Mapped[str | None] = mapped_column(String(30), index=True)   # só dígitos
    numero_cnj_fmt: Mapped[str | None] = mapped_column(String(30))
    texto: Mapped[str] = mapped_column(Text, nullable=False, default="")
    data_disponibilizacao: Mapped[date | None] = mapped_column(Date, index=True)
    tribunal: Mapped[str | None] = mapped_column(String(20))
    tipo_comunicacao: Mapped[str | None] = mapped_column(String(120))
    orgao: Mapped[str | None] = mapped_column(String(255))
    link: Mapped[str | None] = mapped_column(Text)
    hash: Mapped[str] = mapped_column(String(64), index=True)   # dedupe
    # NOVA (a triar) → TRIADA (virou prazo) | IGNORADA
    status: Mapped[str] = mapped_column(String(20), default="NOVA", index=True)
    deadline_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
