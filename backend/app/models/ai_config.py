"""AIProviderConfig — múltiplas IAs (BYOK) por usuário.

Substitui o desenho anterior de 1 config global por usuário (colunas
`User.ai_provider/ai_api_key_enc/ai_model/ai_enabled`, mantidas por
compatibilidade — ver `app/integrations/byok.py`). Cada linha aqui é uma IA
cadastrada (provedor + credencial + modelo), permitindo múltiplas contas do
mesmo ou de provedores diferentes, com uma marcada como padrão."""
from sqlalchemy import String, Boolean, ForeignKey, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime
from app.db.base import Base


class AIProviderConfig(Base):
    """Uma IA cadastrada por um usuário (BYOK multi-provedor, Fase 137.1).

    `credentials_enc` guarda um JSON cifrado (Fernet, mesmo mecanismo de
    `TenantIntegration`/`GoogleIntegration`) — hoje só `{"api_key": ...}`;
    OAuth (Fase 137.2) e outros formatos de credencial usam a mesma coluna.
    `priority` existe desde já mas só passa a ser lido na Fase 137.3
    (fallback ordenado) — evita uma 2ª migração de schema quando essa fase
    chegar."""
    __tablename__ = "ai_provider_configs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)  # anthropic | openai | gemini | grok | deepseek | openrouter | ollama
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    auth_method: Mapped[str] = mapped_column(String(20), nullable=False, default="api_key")  # api_key | oauth | none
    credentials_enc: Mapped[str | None] = mapped_column(Text)  # JSON cifrado (Fernet)
    model: Mapped[str | None] = mapped_column(String(80))
    base_url: Mapped[str | None] = mapped_column(String(255))  # obrigatório só pra ollama (self-hosted)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int | None] = mapped_column(Integer)  # reservado — Fase 137.3 (fallback ordenado)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ATIVA")  # ATIVA | ERRO
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
