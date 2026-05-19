"""Schemas para processos judiciais com validação CNJ."""
import re
from pydantic import BaseModel, field_validator


AREAS_DIREITO = {
    "CIVIL", "TRABALHISTA", "PENAL", "TRIBUTARIO", "AMBIENTAL",
    "ADMINISTRATIVO", "PREVIDENCIARIO", "CONSUMIDOR", "FAMILIA", "IMOBILIARIO",
}

FASES = {"CONHECIMENTO", "EXECUCAO", "RECURSAL", "LIQUIDACAO", "CUMPRIMENTO"}

POLOS = {"ATIVO", "PASSIVO", "LITISCONSORTE"}


class ProcessCreate(BaseModel):
    numero_cnj: str | None = None
    tribunal: str
    vara: str | None = None
    comarca: str | None = None
    uf: str | None = None
    tipo_acao: str | None = None
    area_direito: str | None = None
    fase: str | None = None
    valor_causa: float | None = None
    client_id: str | None = None
    parte_contraria: str | None = None
    polo: str | None = None
    oab_responsavel: str | None = None
    monitoring_active: bool = True

    @field_validator("numero_cnj")
    @classmethod
    def validate_cnj(cls, v):
        if v is None:
            return v
        pattern = r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$"
        if not re.match(pattern, v):
            raise ValueError("Número CNJ inválido (formato: NNNNNNN-DD.AAAA.J.TT.OOOO)")
        return v

    @field_validator("area_direito")
    @classmethod
    def validate_area(cls, v):
        if v and v not in AREAS_DIREITO:
            raise ValueError(f"Área inválida. Opções: {', '.join(sorted(AREAS_DIREITO))}")
        return v

    @field_validator("fase")
    @classmethod
    def validate_fase(cls, v):
        if v and v not in FASES:
            raise ValueError(f"Fase inválida. Opções: {', '.join(sorted(FASES))}")
        return v

    @field_validator("polo")
    @classmethod
    def validate_polo(cls, v):
        if v and v not in POLOS:
            raise ValueError(f"Polo inválido. Opções: {', '.join(sorted(POLOS))}")
        return v

    @field_validator("valor_causa")
    @classmethod
    def validate_valor(cls, v):
        if v is not None and v < 0:
            raise ValueError("Valor da causa não pode ser negativo")
        return v

    @field_validator("uf")
    @classmethod
    def validate_uf(cls, v):
        if v is None:
            return v
        ufs = {
            "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
            "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
            "RS", "RO", "RR", "SC", "SP", "SE", "TO",
        }
        if v.upper() not in ufs:
            raise ValueError("UF inválida")
        return v.upper()


class ProcessUpdate(ProcessCreate):
    tribunal: str | None = None  # type: ignore[assignment]
    monitoring_active: bool | None = None  # type: ignore[assignment]
