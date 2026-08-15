from sqlalchemy import String, Boolean, ForeignKey, Text, Numeric, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime, date
from decimal import Decimal
from app.db.base import Base


class LegalProcess(Base):
    __tablename__ = "legal_processes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "numero_cnj", name="uq_tenant_processo_cnj"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    numero_cnj: Mapped[str | None] = mapped_column(String(25), index=True)  # uniqueness via uq_tenant_processo_cnj
    numero_original: Mapped[str | None] = mapped_column(String(50))
    tribunal: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    vara: Mapped[str | None] = mapped_column(String(255))
    comarca: Mapped[str | None] = mapped_column(String(255))
    uf: Mapped[str | None] = mapped_column(String(2))
    tipo_acao: Mapped[str | None] = mapped_column(String(255))
    area_direito: Mapped[str | None] = mapped_column(String(100), index=True)  # CIVIL, TRABALHISTA, PENAL, TRIBUTARIO
    fase: Mapped[str | None] = mapped_column(String(50))   # CONHECIMENTO, EXECUCAO, RECURSAL
    situacao: Mapped[str] = mapped_column(String(50), default="ATIVO", index=True)
    desfecho: Mapped[str | None] = mapped_column(String(20))  # EXITO, PARCIAL, ACORDO, DERROTA (ao encerrar)
    # Fase 138.4 — tese jurídica argumentada, escolhida manualmente numa
    # lista controlada por tenant (app/models/tese.py). SET NULL ao apagar
    # a tese: desativar/remover uma tese não derruba os processos já ligados.
    tese_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("teses.id", ondelete="SET NULL"), nullable=True, index=True)
    valor_causa: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    client_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id"), index=True)
    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    oab_responsavel: Mapped[str | None] = mapped_column(String(20))
    parte_contraria: Mapped[str | None] = mapped_column(String(500))
    polo: Mapped[str | None] = mapped_column(String(10))   # ATIVO, PASSIVO, LITISCONSORTE
    distribuicao_data: Mapped[date | None] = mapped_column(Date)
    ultimo_andamento_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proximo_prazo_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    monitoring_active: Mapped[bool] = mapped_column(Boolean, default=True)
    descricao: Mapped[str | None] = mapped_column(Text)
    fonte: Mapped[str | None] = mapped_column(String(30), index=True)  # OAB, MANUAL (Fase 86)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    client: Mapped["Client"] = relationship(back_populates="processes")
    movements: Mapped[list["ProcessMovement"]] = relationship(back_populates="process", cascade="all, delete-orphan")
    deadlines: Mapped[list["ProcessDeadline"]] = relationship(back_populates="process", cascade="all, delete-orphan")
    parties: Mapped[list["ProcessParty"]] = relationship(back_populates="process", cascade="all, delete-orphan")
    # Fase 180 — passive_deletes=True: sem isso, o SQLAlchemy carrega os
    # documentos e zera process_id em Python ANTES do DELETE (comportamento
    # padrão do ORM pra relationship sem cascade="delete"), sobrescrevendo o
    # ON DELETE CASCADE do banco (achado real durante a verificação empírica
    # da Fase 180 — o documento sobrevivia com process_id=NULL em vez de ser
    # apagado junto do processo). Com passive_deletes, o ORM não gerencia a
    # coleção no delete — confia inteiramente na constraint do banco.
    documents: Mapped[list["Document"]] = relationship(back_populates="process", passive_deletes=True)
    team: Mapped[list["ProcessTeamMember"]] = relationship(back_populates="process", cascade="all, delete-orphan")


class ProcessTeamMember(Base):
    """Equipe do processo (N:N processo↔advogados). `responsavel_id` do processo
    continua como o principal; a equipe habilita a "Minha Área" de cada advogado
    e as notificações direcionadas."""
    __tablename__ = "process_team"
    __table_args__ = (
        UniqueConstraint("process_id", "user_id", name="uq_process_team_member"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    process_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("legal_processes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    papel: Mapped[str] = mapped_column(String(20), default="COLABORADOR")  # RESPONSAVEL | COLABORADOR
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    process: Mapped["LegalProcess"] = relationship(back_populates="team")


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
    # Heurística: o andamento provavelmente inicia um prazo (intimação, despacho c/ prazo…).
    possivel_prazo: Mapped[bool] = mapped_column(Boolean, default=False)
    # Dedup canônico (Fase 72): sha256(dia|descrição normalizada) — ver services/movements_import.py
    dedup_hash: Mapped[str | None] = mapped_column(String(64), index=True)
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
    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    # Faixas de alerta (3/7/15 dias) já notificadas — evita reenvio diário e
    # torna o alerta resiliente a downtime do worker (não depende de data exata).
    alertas_enviados: Mapped[list | None] = mapped_column(JSONB, default=list)
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
    origem: Mapped[str | None] = mapped_column(String(20))  # MANUAL, PDPJ, ESCAVADOR, JUDIT, JUSBRASIL, IMPORTADO
    # Fase 179 — vínculo opcional a um cliente já cadastrado (autor/réu que
    # também é cliente do escritório). SET NULL ao apagar o cliente: a parte
    # continua existindo no histórico do processo, só perde o vínculo.
    client_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)

    process: Mapped["LegalProcess"] = relationship(back_populates="parties")
    client: Mapped["Client | None"] = relationship()
