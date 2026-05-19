"""Schemas para lançamentos financeiros."""
from pydantic import BaseModel, field_validator
from decimal import Decimal
from datetime import date


TIPOS = {"RECEITA", "DESPESA"}
STATUS = {"PENDENTE", "PAGO", "CANCELADO", "VENCIDO"}


class FinancialEntryCreate(BaseModel):
    tipo: str
    categoria: str | None = None
    client_id: str | None = None
    process_id: str | None = None
    descricao: str
    valor: float
    data_vencimento: date | None = None
    status: str = "PENDENTE"

    @field_validator("tipo")
    @classmethod
    def validate_tipo(cls, v):
        if v not in TIPOS:
            raise ValueError(f"tipo deve ser: {', '.join(TIPOS)}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in STATUS:
            raise ValueError(f"status deve ser: {', '.join(STATUS)}")
        return v

    @field_validator("valor")
    @classmethod
    def validate_valor(cls, v):
        if v < 0:
            raise ValueError("Valor não pode ser negativo")
        d = Decimal(str(v))
        if d.as_tuple().exponent < -2:
            raise ValueError("Valor deve ter no máximo 2 casas decimais")
        return v


class FinancialEntryUpdate(BaseModel):
    descricao: str | None = None
    valor: float | None = None
    categoria: str | None = None
    data_vencimento: date | None = None
    status: str | None = None

    @field_validator("valor")
    @classmethod
    def validate_valor(cls, v):
        if v is not None and v < 0:
            raise ValueError("Valor não pode ser negativo")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v and v not in STATUS:
            raise ValueError(f"status deve ser: {', '.join(STATUS)}")
        return v
