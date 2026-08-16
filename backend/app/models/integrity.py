"""Programa de Integridade — aceite do Código de Conduta, Canal de Denúncias,
e (Fase 189) os 3 itens do "Próximos passos do programa": Matriz de Riscos,
Treinamentos Obrigatórios e Comitê de Integridade."""
from sqlalchemy import String, Boolean, ForeignKey, Text, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime
from app.db.base import Base


class ConductAcceptance(Base):
    """Aceite registrado do Código de Conduta (por versão do documento)."""
    __tablename__ = "conduct_acceptances"
    __table_args__ = (UniqueConstraint("user_id", "version", name="uq_conduct_user_version"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntegrityReport(Base):
    """Relato do Canal de Denúncias (com opção de anonimato).

    Se `anonimo=True`, `created_by` fica NULO — o anonimato é garantido no
    registro (não apenas na exibição)."""
    __tablename__ = "integrity_reports"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    categoria: Mapped[str] = mapped_column(String(40), nullable=False)  # ETICA, CONFLITO_INTERESSES, DADOS_LGPD, USO_DE_IA, ASSEDIO, OUTROS
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    anonimo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ABERTO", index=True)  # ABERTO, EM_ANALISE, RESOLVIDO
    resolucao: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class IntegrityRisk(Base):
    """Matriz de Riscos de Integridade (Fase 189.1) — mapeamento periódico
    de riscos de conduta/conformidade com controles e responsável."""
    __tablename__ = "integrity_risks"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    risco: Mapped[str] = mapped_column(String(200), nullable=False)
    categoria: Mapped[str] = mapped_column(String(40), nullable=False)  # mesmas categorias do Canal de Denúncias
    probabilidade: Mapped[str] = mapped_column(String(10), nullable=False)  # BAIXA, MEDIA, ALTA
    impacto: Mapped[str] = mapped_column(String(10), nullable=False)  # BAIXO, MEDIO, ALTO
    controles: Mapped[str] = mapped_column(Text, nullable=False)
    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ATIVO")  # ATIVO, MITIGADO, ENCERRADO
    ultima_revisao_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class IntegrityTraining(Base):
    """Trilha de treinamento obrigatório (Fase 189.2) — ética, LGPD ou uso
    responsável de IA. Conclusão é registrada por usuário em
    `IntegrityTrainingCompletion`."""
    __tablename__ = "integrity_trainings"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    categoria: Mapped[str] = mapped_column(String(20), nullable=False)  # ETICA, LGPD, USO_DE_IA
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    obrigatorio: Mapped[bool] = mapped_column(Boolean, default=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class IntegrityTrainingCompletion(Base):
    """Conclusão de um usuário numa trilha — único por (user_id, training_id),
    mesmo padrão de `ConductAcceptance`."""
    __tablename__ = "integrity_training_completions"
    __table_args__ = (UniqueConstraint("user_id", "training_id", name="uq_training_user"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    training_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("integrity_trainings.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntegrityCommitteeCase(Base):
    """Caso avaliado pelo Comitê de Integridade (Fase 189.3) — pode
    referenciar um relato do Canal de Denúncias (`report_id`) ou ser uma
    deliberação de política pura (`report_id` nulo)."""
    __tablename__ = "integrity_committee_cases"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    report_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("integrity_reports.id", ondelete="SET NULL"), nullable=True)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="EM_ANALISE")  # EM_ANALISE, DECIDIDO
    decisao: Mapped[str | None] = mapped_column(Text)
    membros: Mapped[list] = mapped_column(JSONB, default=list)  # nomes/emails dos participantes da deliberação
    decided_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
