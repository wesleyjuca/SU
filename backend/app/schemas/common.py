"""Schemas comuns e validadores brasileiros."""
import re
from pydantic import BaseModel, field_validator


def _digits_only(v: str) -> str:
    return re.sub(r"\D", "", v)


def _validate_cpf(cpf: str) -> bool:
    cpf = _digits_only(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in range(9, 11):
        total = sum(int(cpf[j]) * (i + 1 - j) for j in range(i))
        d = (total * 10 % 11) % 10
        if d != int(cpf[i]):
            return False
    return True


def _validate_cnpj(cnpj: str) -> bool:
    cnpj = _digits_only(cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for weights, pos in [(weights1, 12), (weights2, 13)]:
        total = sum(int(cnpj[i]) * w for i, w in enumerate(weights))
        d = (total % 11)
        d = 0 if d < 2 else 11 - d
        if d != int(cnpj[pos]):
            return False
    return True


def _validate_cnj(numero: str) -> bool:
    pattern = r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$"
    return bool(re.match(pattern, numero))


class CPFStr(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not isinstance(v, str):
            raise ValueError("CPF deve ser uma string")
        if not _validate_cpf(v):
            raise ValueError("CPF inválido")
        return _digits_only(v)


class CNJStr(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not isinstance(v, str):
            raise ValueError("Número CNJ deve ser uma string")
        if not _validate_cnj(v):
            raise ValueError("Número CNJ inválido (formato: NNNNNNN-DD.AAAA.J.TT.OOOO)")
        return v


class PaginationParams(BaseModel):
    limit: int = 50
    offset: int = 0

    @field_validator("limit")
    @classmethod
    def limit_range(cls, v):
        if v < 1 or v > 200:
            raise ValueError("limit deve estar entre 1 e 200")
        return v

    @field_validator("offset")
    @classmethod
    def offset_positive(cls, v):
        if v < 0:
            raise ValueError("offset deve ser >= 0")
        return v
