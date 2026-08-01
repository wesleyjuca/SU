"""JurisprudenciaIngerida — controle de idempotência da ingestão automática
de jurisprudência/legislação (Fase 138.1, pipeline STJ dados abertos).

1 linha por documento externo já processado, chave de idempotência
`(fonte, fonte_documento_id)` — se o mesmo documento aparecer de novo numa
sincronização futura (ex.: re-publicação, reprocessamento manual), a
sincronização detecta e pula, sem duplicar chunks no Qdrant.

Não duplica o texto completo do documento aqui — o conteúdo já vai pro
Qdrant via `ingest_document()` (chunk+embed+upsert); esta tabela guarda só o
necessário pra idempotência/observabilidade/retry (metadados extraídos,
status, erro), o mesmo espírito de `AICallLog` (Fase 137.7): fonte de
verdade em outro lugar, aqui é só controle."""
from sqlalchemy import String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime
from app.db.base import Base


class JurisprudenciaIngerida(Base):
    __tablename__ = "jurisprudencia_ingerida"
    __table_args__ = (
        UniqueConstraint("fonte", "fonte_documento_id", name="uq_jurisprudencia_ingerida_fonte_doc"),
        Index("ix_jurisprudencia_ingerida_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fonte: Mapped[str] = mapped_column(String(30), nullable=False)  # stj_dados_abertos
    fonte_documento_id: Mapped[str] = mapped_column(String(255), nullable=False)
    collection_alvo: Mapped[str] = mapped_column(String(30), nullable=False)  # jurisprudencia | legislacao
    metadata_extraida: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDENTE")  # PENDENTE | EMBEDDED | FALHOU
    erro: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
