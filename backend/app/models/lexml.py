"""Acervo de normas do LexML — metadados estruturados + o que é do escritório.

Duas tabelas, separadas por uma razão de desenho, não de conveniência:

- **`lexml_normas` NÃO tem `tenant_id`, de propósito.** Uma Lei federal é a
  mesma para todos os escritórios: ingerir uma vez, todos consultam. É a mesma
  decisão já aplicada à collection `legislacao` do Qdrant, que é pública
  (`rag/retrieval.py::PRIVATE_COLLECTIONS` não a inclui). Duplicar a mesma
  norma por tenant multiplicaria armazenamento e custo de ingestão sem ganho.
- **`lexml_norma_tenant` tem**, porque favorito, vínculo com processo e
  anotação são do escritório e nunca podem vazar entre tenants.

Sobre o texto integral: guardado sob demanda, não em massa (decisão do dono do
produto). O LexML é um agregador de metadados — o texto vive no órgão de
origem, e replicar o acervo inteiro num produto comercial é a mesma classe de
questão já registrada em `docs/juridico/DATAJUD_TERMO_DE_USO.md`, hoje
aguardando parecer. `texto_obtido_em` marca a idade do que foi cacheado.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LexmlNorma(Base):
    """Metadados de uma norma do acervo LexML. Compartilhada entre tenants."""

    __tablename__ = "lexml_normas"
    __table_args__ = (
        UniqueConstraint("urn", name="uq_lexml_normas_urn"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # A URN é a CHAVE NATURAL — identificador jurídico externo, estável e
    # citável (`urn:lex:br:federal:lei:1990-09-11;8078`). O `id` UUID existe
    # só para servir de FK interna; toda lógica de dedup/idempotência usa a URN.
    urn: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, index=True)

    titulo: Mapped[str | None] = mapped_column(Text)
    ementa: Mapped[str | None] = mapped_column(Text)

    # Derivados da URN quando possível (ver services/lexml_urn.py). Nulos
    # quando a URN não segue a forma esperada — nunca "consertados" por
    # heurística, o dado fica nulo e a URN crua é preservada.
    tipo_norma: Mapped[str | None] = mapped_column(String(80), index=True)
    numero: Mapped[str | None] = mapped_column(String(40))
    ano: Mapped[int | None] = mapped_column(Integer, index=True)
    autoridade: Mapped[str | None] = mapped_column(String(160))
    localidade: Mapped[str | None] = mapped_column(String(80))
    data_publicacao: Mapped[date | None] = mapped_column(DateTime(timezone=True))

    url_fonte: Mapped[str | None] = mapped_column(Text)

    # Sob demanda: nulo = nunca buscado. `texto_obtido_em` permite revalidar
    # por idade sem precisar de uma coluna de status separada.
    texto_integral: Mapped[str | None] = mapped_column(Text)
    texto_obtido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    metadata_json: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LexmlNormaTenant(Base):
    """Relação de UM escritório com uma norma: favorito, vínculo, anotação.

    Entra no ciclo de esquecimento LGPD: `process_id` é alcançável a partir do
    cliente (`legal_processes.client_id`), e `anotacao` é texto livre escrito
    pelo escritório sobre um caso. É a 10ª tabela desta classe no projeto — as
    9 anteriores viraram achado de auditoria por terem sido esquecidas.
    """

    __tablename__ = "lexml_norma_tenant"
    __table_args__ = (
        UniqueConstraint("tenant_id", "norma_id", "process_id", name="uq_lexml_norma_tenant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    norma_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lexml_normas.id", ondelete="CASCADE"), nullable=False, index=True
    )

    favorito: Mapped[bool] = mapped_column(Boolean, default=False)
    process_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("legal_processes.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE")
    )
    anotacao: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
