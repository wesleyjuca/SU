"""Schemas para usuários."""
import re
from pydantic import BaseModel, field_validator, EmailStr


ROLES = {"ADMIN", "SOCIO", "ADVOGADO", "PARALEGAL", "ASSISTENTE"}


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: str = "ASSISTENTE"
    oab_number: str | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in ROLES:
            raise ValueError(f"role deve ser: {', '.join(sorted(ROLES))}")
        return v

    @field_validator("oab_number")
    @classmethod
    def validate_oab(cls, v):
        if v is None:
            return v
        pattern = r"^\d{4,6}[A-Z]{2}$"
        if not re.match(pattern, v.upper().replace("/", "").replace("-", "")):
            raise ValueError("OAB inválida (formato: 123456UF)")
        return v.upper()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Senha deve ter no mínimo 8 caracteres")
        return v


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    oab_number: str | None = None
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v and v not in ROLES:
            raise ValueError(f"role deve ser: {', '.join(sorted(ROLES))}")
        return v
