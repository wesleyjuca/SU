"""Schemas Pydantic para clientes com validação brasileira."""
import re
from pydantic import BaseModel, field_validator


def _digits_only(v: str) -> str:
    return re.sub(r"\D", "", v)


class ClientCreate(BaseModel):
    tipo: str
    nome_completo: str
    razao_social: str | None = None
    email: str | None = None
    telefone: str | None = None
    whatsapp: str | None = None
    cpf: str | None = None
    cnpj: str | None = None
    origem: str | None = None
    status: str = "PROSPECTO"
    observacoes: str | None = None
    lgpd_consent: bool = False

    @field_validator("tipo")
    @classmethod
    def validate_tipo(cls, v):
        if v not in ("PF", "PJ"):
            raise ValueError("tipo deve ser PF ou PJ")
        return v

    @field_validator("cpf")
    @classmethod
    def validate_cpf(cls, v):
        if v is None:
            return v
        from app.schemas.common import _validate_cpf
        if not _validate_cpf(v):
            raise ValueError("CPF inválido")
        return _digits_only(v)

    @field_validator("cnpj")
    @classmethod
    def validate_cnpj(cls, v):
        if v is None:
            return v
        from app.schemas.common import _validate_cnpj
        if not _validate_cnpj(v):
            raise ValueError("CNPJ inválido")
        return _digits_only(v)

    @field_validator("telefone", "whatsapp")
    @classmethod
    def validate_telefone(cls, v):
        if v is None:
            return v
        digits = _digits_only(v)
        if len(digits) < 10 or len(digits) > 13:
            raise ValueError("Telefone inválido (mínimo 10 dígitos, máximo 13)")
        return digits

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        valid = {"PROSPECTO", "ATIVO", "INATIVO", "VIP"}
        if v not in valid:
            raise ValueError(f"status deve ser um de: {', '.join(valid)}")
        return v


class ClientUpdate(ClientCreate):
    tipo: str | None = None  # type: ignore[assignment]
    nome_completo: str | None = None  # type: ignore[assignment]
    status: str | None = None  # type: ignore[assignment]
    lgpd_consent: bool | None = None  # type: ignore[assignment]
