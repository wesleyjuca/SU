"""Config editável dos prompts/anexos dos agentes nativos (Fase 140.1).

Tabelas plataforma-wide (sem tenant_id) — os 19 agentes são um catálogo
único, compartilhado por todos os escritórios do SaaS (app/agents/brain/
orchestrator.py::resolve_agent_class), não há registro por tenant hoje."""
from sqlalchemy import String, ForeignKey, Text, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime
from app.db.base import Base


class AgentPromptConfig(Base):
    """Override do system prompt de um agente nativo.

    Chave estável = agent_name (mesma string usada no `agent_map` de
    resolve_agent_class) + prompt_slot (quase todo agente só tem
    "primary"; crm_agent é a exceção). prompt_text NULL = "usa o default
    hardcoded em Python" — fail-soft por design, nunca quebra um agente
    por falta de linha na tabela."""
    __tablename__ = "agent_prompt_configs"
    __table_args__ = (UniqueConstraint("agent_name", "prompt_slot", name="uq_agent_prompt_slot"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    prompt_slot: Mapped[str] = mapped_column(String(50), nullable=False, default="primary")
    prompt_text: Mapped[str | None] = mapped_column(Text)
    versao: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    versions: Mapped[list["AgentPromptVersion"]] = relationship(back_populates="config", cascade="all, delete-orphan")


class AgentPromptVersion(Base):
    """Snapshot do texto ANTERIOR a cada edição — mesmo padrão de
    DocumentVersion (app/models/document.py): guarda o estado antigo antes
    de sobrescrever, nunca o novo."""
    __tablename__ = "agent_prompt_versions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("agent_prompt_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_text: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    change_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    config: Mapped["AgentPromptConfig"] = relationship(back_populates="versions")


class AgentAttachment(Base):
    """Arquivo de contexto extra anexado a um agente nativo. Mesmo padrão de
    armazenamento do Document.upload (base64 data-URL em Text — sem S3/
    MinIO, débito técnico já documentado em CLAUDE.md), em tabela própria
    (não linkada a Document — Document carrega process_id/client_id/fluxo
    RASCUNHO→PROTOCOLADO/tenant_id, nada disso se aplica a "anexo de config
    de agente")."""
    __tablename__ = "agent_attachments"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    data_url: Mapped[str | None] = mapped_column(Text)
    # Fase 190 — mesmo padrão de Document.arquivo_storage_key (Fase 141):
    # NULL = binário segue inline em data_url (caminho legado, sem backfill);
    # setado = bytes vivem no object storage S3-compatível nessa key.
    storage_key: Mapped[str | None] = mapped_column(String(500))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
