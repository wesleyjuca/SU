from sqlalchemy import String, Boolean, ForeignKey, UniqueConstraint, Text, Numeric, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
import uuid
from datetime import datetime
from app.db.base import Base
from sqlalchemy import DateTime, func


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    oab_number: Mapped[str | None] = mapped_column(String(20))
    oab_uf: Mapped[str | None] = mapped_column(String(2))
    telefone: Mapped[str | None] = mapped_column(String(20))  # WhatsApp (Fase 70)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="ASSISTENTE")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    mfa_secret: Mapped[str | None] = mapped_column(String(255))
    # ── BYOK: IA própria do usuário (economiza tokens do sistema) ──
    ai_provider: Mapped[str | None] = mapped_column(String(20))       # anthropic | gemini
    ai_api_key_enc: Mapped[str | None] = mapped_column(Text)          # chave cifrada em repouso
    ai_model: Mapped[str | None] = mapped_column(String(80))
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Fase 137.6 — modo de uso global (balanceamento automático) entre as
    # várias AIProviderConfig do usuário. NULL = "padrao" (ordem manual de
    # sempre). Ver app/services/ai_balance.py.
    ai_balance_mode: Mapped[str | None] = mapped_column(String(20))
    # Fase 206.2 — preferências de notificação persistentes por tipo de evento
    # (antes só localStorage, perdidas ao trocar de navegador/dispositivo).
    # Chave = pref key (ver TIPO_PARA_PREF em app/services/notification.py),
    # valor = bool. Chave ausente = notifica (default opt-in, sem regressão
    # pra quem nunca abriu a tela de preferências).
    notification_prefs: Mapped[dict | None] = mapped_column(JSONB)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    linked_client_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id"), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    permissions: Mapped[list["UserPermission"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    sessions: Mapped[list["Session"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserPermission(Base):
    __tablename__ = "user_permissions"
    __table_args__ = (UniqueConstraint("user_id", "resource", "action"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    resource: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="permissions")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="sessions")


class AITaskOverride(Base):
    """Override de IA por tipo de tarefa (BYOK por área) — Fase 137.4.

    `provider_config_id` (se presente) referencia uma `AIProviderConfig`
    INTEIRA (provider+chave+modelo próprios), substituindo a IA padrão pra
    essa tarefa. `model` (string) é o caminho legado da Fase 137.1 — só troca
    o MODELO, mantendo o provedor/chave da IA padrão — mantido por
    compatibilidade retroativa e usado como fallback secundário quando
    `provider_config_id` está vazio ou aponta pra uma config removida."""
    __tablename__ = "ai_task_overrides"
    __table_args__ = (UniqueConstraint("user_id", "task_type", name="uq_ai_override_user_task"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    task_type: Mapped[str] = mapped_column(String(60), nullable=False)
    model: Mapped[str | None] = mapped_column(String(80))
    provider_config_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_provider_configs.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AIBudgetLimit(Base):
    """Teto mensal de gasto de IA por usuário (USD), definido por ADMIN/SÓCIO.

    Ao atingir `alert_pct` do teto, o usuário recebe um alerta; ao estourar o
    teto, novas execuções de agentes são bloqueadas (bloqueio suave — o admin
    pode elevar/remover o limite a qualquer momento)."""
    __tablename__ = "ai_budget_limits"
    __table_args__ = (UniqueConstraint("user_id", name="uq_ai_budget_user"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    monthly_limit_usd: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    alert_pct: Mapped[int] = mapped_column(Integer, default=80)  # % do teto que dispara alerta
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
