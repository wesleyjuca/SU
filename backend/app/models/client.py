from sqlalchemy import String, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime
from app.db.base import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)  # PF, PJ
    cpf: Mapped[str | None] = mapped_column(String(255))    # encrypted at rest
    cnpj: Mapped[str | None] = mapped_column(String(255))   # encrypted at rest
    nome_completo: Mapped[str] = mapped_column(String(500), nullable=False)
    razao_social: Mapped[str | None] = mapped_column(String(500))
    email: Mapped[str | None] = mapped_column(String(255))
    telefone: Mapped[str | None] = mapped_column(String(20))
    whatsapp: Mapped[str | None] = mapped_column(String(20))
    endereco_json: Mapped[dict | None] = mapped_column(JSONB)
    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    origem: Mapped[str | None] = mapped_column(String(100))   # site, indicacao, crm_agent
    status: Mapped[str] = mapped_column(String(50), default="PROSPECTO")
    # Fase 151 — separado de `status` (lifecycle: PROSPECTO/ATIVO/INATIVO).
    # crm_agent.classify_client gravava o segmento (PLATINUM/GOLD/SILVER/
    # REGULAR) direto em `status`, colidindo com o dropdown de lifecycle do
    # frontend.
    segmento: Mapped[str | None] = mapped_column(String(20))
    lgpd_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    lgpd_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observacoes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    contacts: Mapped[list["ClientContact"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    interactions: Mapped[list["ClientInteraction"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    processes: Mapped[list["LegalProcess"]] = relationship(back_populates="client")


class ClientContact(Base):
    __tablename__ = "client_contacts"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    cargo: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(255))
    telefone: Mapped[str | None] = mapped_column(String(20))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    client: Mapped["Client"] = relationship(back_populates="contacts")


class ClientPortalAccess(Base):
    """Fase 234 — acesso ao Portal do Cliente via link temporário, separado
    do cadastro de usuários internos. 1 registro por cliente (regenerar
    substitui token/validade no lugar); `portal_user_id` aponta pra um
    `User` técnico oculto (role=CLIENT, senha aleatória nunca exposta,
    nunca listado em `GET /users`) que só existe pra reaproveitar o
    mecanismo de JWT/sessão já usado por todo o sistema
    (`get_current_user`, `/auth/refresh`) sem reescrevê-lo. `token_hash`
    é o SHA-256 (`hash_token()`, mesmo padrão de `Session.token_hash`) —
    o token bruto nunca é persistido, só devolvido uma vez na geração."""
    __tablename__ = "client_portal_access"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, unique=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    portal_user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClientInteraction(Base):
    __tablename__ = "client_interactions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    # Fase 153 — endurecimento defensivo em profundidade (não é exploração
    # conhecida hoje: os 2 caminhos de escrita já resolvem client_id dentro
    # do tenant do usuário antes de persistir). Nullable, sem backfill.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    tipo: Mapped[str | None] = mapped_column(String(50))  # EMAIL, LIGACAO, REUNIAO, WHATSAPP, SISTEMA
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped["Client"] = relationship(back_populates="interactions")
