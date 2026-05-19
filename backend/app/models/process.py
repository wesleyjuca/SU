from sqlalchemy import String, Boolean, ForeignKey, Text, Numeric, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB, ARRAY
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime, date
from decimal import Decimal
from app.db.base import Base


class LegalProcess(Base):
    __tablename__ = "legal_processes"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    numero_cnj: Mapped[str | None] = mapped_column(String(25), unique=True, index=True)
    numero_original: Mapped[str | None] = mapped_column(String(50))
    tribunal: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    vara: Mapped[str | None] = mapped_column(String(255))
    comarca: Mapped[str | None] = mapped_column(String(255))
    uf: Mapped[str | None] = mapped_column(String(2))
    tipo_acao: Mapped[str | None] = mapped_column(String(255))
    area_direito: Mapped[str | None] = mapped_column(String(100), index=True)  # CIVIL, TRABALHISTA, PENAL, TRIBUTARIO
    fase: Mapped[str | None] = mapped_column(String(50))   # CONHECIMENTO, EXECUCAO, RECURSAL
    situacao: Mapped[str] = mapped_column(String(50), default="ATIVO", index=True)
    valor_causa: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    client_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id"), index=True)
    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    oab_responsavel: Mapped[str | None] = mapped_column(String(20))
    parte_contraria: Mapped[str | None] = mapped_column(String(500))
    polo: Mapped[str | None] = mapped_column(String(10))   # ATIVO, PASSIVO, LITISCONSORTE
    distribuicao_data: Mapped[date | None] = mapped_column(Date)
    ultimo_andamento_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proximo_prazo_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    monitoring_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    client: Mapped["Client"] = relationship(back_populates="processes")
    movements: Mapped[list["ProcessMovement"]] = relationship(back_populates="process", cascade="all, delete-orphan")
    deadlines: Mapped[list["ProcessDeadline"]] = relationship(back_populates="process", cascade="all, delete-orphan")
    parties: Mapped[list["ProcessParty"]] = relationship(back_populates="process", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(back_populates="process")


class ProcessMovement(Base):
    __tablename__ = "process_movements"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    process_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("legal_processes.id", ondelete="CASCADE"), nullable=False, index=True)
    data_movimento: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[str | None] = mapped_column(String(50))   # DESPACHO, SENTENCA, ACORDAO, INTIMACAO
    documento_url: Mapped[str | None] = mapped_column(Text)
    raw_html: Mapped[str | None] = mapped_column(Text)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    process: Mapped["LegalProcess"] = relationship(back_populates="movements")


class ProcessDeadline(Base):
    __tablename__ = "process_deadlines"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    process_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("legal_processes.id", ondelete="CASCADE"), nullable=False)
    movement_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("process_movements.id"))
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    data_prazo: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    data_fatal: Mapped[date | None] = mapped_column(Date)
    tipo: Mapped[str | None] = mapped_column(String(50))  # CONTESTACAO, RECURSO, MANIFESTACAO
    status: Mapped[str] = mapped_column(String(20), default="PENDENTE", index=True)
    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    process: Mapped["LegalProcess"] = relationship(back_populates="deadlines")


class ProcessParty(Base):
    __tablename__ = "process_parties"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    process_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("legal_processes.id", ondelete="CASCADE"), nullable=False)
    tipo: Mapped[str | None] = mapped_column(String(20))  # AUTOR, REU, ADVOGADO, JUIZ, MP
    nome: Mapped[str | None] = mapped_column(String(500))
    cpf_cnpj: Mapped[str | None] = mapped_column(String(18))
    oab: Mapped[str | None] = mapped_column(String(20))
    polo: Mapped[str | None] = mapped_column(String(10))

    process: Mapped["LegalProcess"] = relationship(back_populates="parties")
