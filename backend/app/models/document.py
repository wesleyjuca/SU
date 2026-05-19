from sqlalchemy import String, Boolean, ForeignKey, Text, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime
from decimal import Decimal
from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    process_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("legal_processes.id"))
    client_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id"))
    tipo: Mapped[str | None] = mapped_column(String(50))   # PETICAO, CONTRATO, PROCURACAO, SENTENCA
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    conteudo_texto: Mapped[str | None] = mapped_column(Text)
    conteudo_html: Mapped[str | None] = mapped_column(Text)
    arquivo_url: Mapped[str | None] = mapped_column(Text)
    arquivo_hash: Mapped[str | None] = mapped_column(String(64))  # SHA-256
    versao: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), default="RASCUNHO")  # RASCUNHO, REVISAO, APROVADO, PROTOCOLADO
    gerado_por_ia: Mapped[bool] = mapped_column(Boolean, default=False)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    process: Mapped["LegalProcess"] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    petition: Mapped["Petition | None"] = relationship(back_populates="document", uselist=False)
    contract: Mapped["Contract | None"] = relationship(back_populates="document", uselist=False)


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    conteudo_html: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    change_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["Document"] = relationship(back_populates="versions")


class Petition(Base):
    __tablename__ = "petitions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    process_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("legal_processes.id"))
    tipo_peticao: Mapped[str | None] = mapped_column(String(100))  # INICIAL, CONTESTACAO, RECURSO
    template_used: Mapped[str | None] = mapped_column(String(100))
    ai_prompt: Mapped[str | None] = mapped_column(Text)
    ai_model: Mapped[str | None] = mapped_column(String(50))
    ai_tokens_used: Mapped[int | None] = mapped_column(Integer)
    review_status: Mapped[str] = mapped_column(String(30), default="PENDENTE_REVISAO")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)

    document: Mapped["Document"] = relationship(back_populates="petition")


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id"))
    tipo: Mapped[str | None] = mapped_column(String(100))  # HONORARIOS, PRESTACAO_SERVICOS
    valor_total: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    data_inicio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_fim: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="RASCUNHO")
    assinaturas: Mapped[dict | None] = mapped_column(JSONB)
    renovacao_auto: Mapped[bool] = mapped_column(Boolean, default=False)

    document: Mapped["Document"] = relationship(back_populates="contract")
