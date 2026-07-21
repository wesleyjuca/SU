"""Histórico de sincronizações do módulo de captura (Fase 72).

Cada execução de captura por OAB, varredura de intimações ou polling de
andamentos registra uma linha — dá observabilidade ao que antes era invisível
(quando rodou, qual fonte, quantos itens, se a fonte respondeu)."""
from sqlalchemy import String, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
import uuid
from datetime import datetime
from app.db.base import Base


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # NULL = execução global (ex.: polling do beat que varre todos os tenants)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    fonte: Mapped[str] = mapped_column(String(30), nullable=False)   # comunica | datajud | multi
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)    # CAPTURA | SCAN | POLLING
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RUNNING")  # RUNNING | OK | ERRO
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
