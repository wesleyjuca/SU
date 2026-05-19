"""Validação de número OAB."""
import re

UFS_VALIDAS = {
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
    "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
}


def validate_oab(numero: str, uf: str) -> bool:
    """Valida formato básico de número OAB."""
    if not numero or not uf:
        return False
    if uf.upper() not in UFS_VALIDAS:
        return False
    numero_limpo = re.sub(r"\D", "", numero)
    return 1 <= len(numero_limpo) <= 9


def format_oab(numero: str, uf: str) -> str:
    """Formata OAB para exibição: SP 123456"""
    numero_limpo = re.sub(r"\D", "", numero)
    return f"{uf.upper()} {numero_limpo}"
