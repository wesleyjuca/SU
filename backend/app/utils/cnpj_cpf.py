"""Validação de CPF e CNPJ conforme algoritmo oficial brasileiro."""
import re


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def validate_cpf(cpf: str) -> bool:
    d = _digits(cpf)
    if len(d) != 11 or len(set(d)) == 1:
        return False
    # Primeiro dígito verificador
    s = sum(int(d[i]) * (10 - i) for i in range(9))
    r = (s * 10) % 11
    if r == 10:
        r = 0
    if r != int(d[9]):
        return False
    # Segundo dígito verificador
    s = sum(int(d[i]) * (11 - i) for i in range(10))
    r = (s * 10) % 11
    if r == 10:
        r = 0
    return r == int(d[10])


def validate_cnpj(cnpj: str) -> bool:
    d = _digits(cnpj)
    if len(d) != 14 or len(set(d)) == 1:
        return False
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    s = sum(int(d[i]) * weights1[i] for i in range(12))
    r = s % 11
    d1 = 0 if r < 2 else 11 - r
    if d1 != int(d[12]):
        return False
    s = sum(int(d[i]) * weights2[i] for i in range(13))
    r = s % 11
    d2 = 0 if r < 2 else 11 - r
    return d2 == int(d[13])


def format_cpf(cpf: str) -> str:
    d = _digits(cpf)
    if len(d) != 11:
        return cpf
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def format_cnpj(cnpj: str) -> str:
    d = _digits(cnpj)
    if len(d) != 14:
        return cnpj
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
