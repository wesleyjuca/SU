"""Tabela de referência de tribunais (Fase 74).

Fonte única dos códigos/índices de tribunal — antes o conhecimento vivia
hardcoded e espalhado por 6+ módulos (o mais completo era `TRIBUNAL_INDICES`
em `integrations/tribunais/cnj.py`). Esta tabela é semeada a partir daquele
mapa na startup, normalizando o código do DF (`TJDF`/`TJDFT`) numa entrada
canônica única.

Tabela nova → criada por `create_all` (não há coluna nova em tabela existente,
então não precisa de ALTER em events.py). Semeadura idempotente lá.
"""
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Tribunal(Base):
    __tablename__ = "tribunais"

    codigo: Mapped[str] = mapped_column(String(12), primary_key=True)   # ex TJSP, TRF3, TRT2
    nome: Mapped[str | None] = mapped_column(String(160))
    tipo: Mapped[str] = mapped_column(String(20), default="ESTADUAL")   # ESTADUAL|FEDERAL|TRABALHO|SUPERIOR
    uf: Mapped[str | None] = mapped_column(String(2))
    datajud_index: Mapped[str | None] = mapped_column(String(60))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
