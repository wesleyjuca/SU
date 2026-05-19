"""Utilitários LGPD — anonimização, consentimento e direito de apagamento."""
import re
import hashlib
from datetime import datetime
from typing import Optional

_CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_CNPJ_RE = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+55\s?)?(?:\(?\d{2}\)?[\s-]?)?\d{4,5}[-\s]?\d{4}\b")


def anonymize_text(text: str) -> str:
    """Remove PII identificável de texto livre."""
    text = _CPF_RE.sub("[CPF REMOVIDO]", text)
    text = _CNPJ_RE.sub("[CNPJ REMOVIDO]", text)
    text = _EMAIL_RE.sub("[EMAIL REMOVIDO]", text)
    text = _PHONE_RE.sub("[TELEFONE REMOVIDO]", text)
    return text


def mask_cpf(cpf: str) -> str:
    """Mascara CPF para exibição: 123.***.***-45"""
    digits = re.sub(r"\D", "", cpf)
    if len(digits) != 11:
        return "***"
    return f"{digits[:3]}.***.***-{digits[-2:]}"


def mask_cnpj(cnpj: str) -> str:
    """Mascara CNPJ para exibição: 12.***.***/**01-45"""
    digits = re.sub(r"\D", "", cnpj)
    if len(digits) != 14:
        return "***"
    return f"{digits[:2]}.***.***/****-{digits[-2:]}"


def hash_sensitive(value: str, salt: str = "") -> str:
    """Hash SHA-256 unidirecional para dados sensíveis (não reversível)."""
    return hashlib.sha256(f"{salt}{value}".encode()).hexdigest()


def check_consent_valid(lgpd_consent: bool, lgpd_consent_at: Optional[datetime]) -> bool:
    """Verifica se consentimento LGPD foi dado e registrado."""
    return lgpd_consent and lgpd_consent_at is not None


def build_consent_record(
    client_id: str,
    tipo_dado: str,
    consentimento: bool,
    base_legal: str,
    ip_address: Optional[str],
    texto_versao: str,
) -> dict:
    """Constrói registro de consentimento LGPD."""
    return {
        "client_id": client_id,
        "tipo_dado": tipo_dado,
        "consentimento": consentimento,
        "base_legal": base_legal,
        "ip_address": ip_address,
        "texto_versao": texto_versao,
        "timestamp": datetime.utcnow().isoformat(),
    }


BASES_LEGAIS = {
    "CONSENTIMENTO": "Art. 7º, I — Consentimento do titular",
    "CONTRATO": "Art. 7º, V — Execução de contrato",
    "OBRIGACAO_LEGAL": "Art. 7º, II — Cumprimento de obrigação legal",
    "INTERESSE_LEGITIMO": "Art. 7º, IX — Legítimo interesse do controlador",
    "EXERCICIO_DIREITO": "Art. 7º, VI — Exercício regular de direitos",
}
