"""AICallLog — 1 linha por chamada de LLM feita com uma AIProviderConfig do
usuário (Fase 137.7, monitoramento por IA).

Sem `user_id`/`tenant_id` de propósito: a posse é sempre via
`config_id -> AIProviderConfig.user_id` — uma fonte de verdade só. Se a
config for removida, `config_id` vira NULL (`ondelete="SET NULL"`) e a linha
simplesmente para de aparecer em qualquer dashboard — aceitável, é dado de
uso/telemetria, não registro jurídico/financeiro que exija retenção
garantida (diferente de `audit_logs`, que é outro sistema, imutável).

Só chamadas com uma `AIProviderConfig` conhecida geram linha aqui — chamadas
usando a chave do sistema (sem BYOK) não têm uma "IA do usuário" pra
atribuir, então ficam de fora por design (ver `app/services/ai_monitoring.py`)."""
from sqlalchemy import String, Boolean, ForeignKey, Integer, Numeric, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime
from app.db.base import Base


class AICallLog(Base):
    __tablename__ = "ai_call_logs"
    __table_args__ = (
        Index("ix_ai_call_logs_config_created", "config_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_provider_configs.id", ondelete="SET NULL"), nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str | None] = mapped_column(String(80))
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(String(255))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
