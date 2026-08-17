"""Assinatura eletrônica de contratos — Clicksign (credenciais do hub).

Fluxo: contrato (Document tipo=CONTRATO) → PDF timbrado → upload no
Clicksign → signatário por e-mail → lista de assinatura. O retorno vem por
webhook; como no pagamento, o payload é DICA — a finalização é confirmada
consultando a API do Clicksign com o token do escritório antes de marcar
o contrato como ASSINADO.
"""
import base64
from datetime import datetime, timezone

import httpx
import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, Contract
from app.services import integration_hub

log = structlog.get_logger()

_TIMEOUT = 30
_BASE = "https://app.clicksign.com"


async def enviar_para_assinatura(
    db: AsyncSession, tenant_id, doc: Document, contract: Contract,
    signatario_email: str, signatario_nome: str,
) -> dict:
    """Sobe o PDF no Clicksign e cria o signatário + lista de assinatura."""
    from app.services.demo_guard import tenant_is_demo
    if await tenant_is_demo(db, tenant_id):
        raise HTTPException(
            status_code=422,
            detail="Ambiente de demonstração: assinatura eletrônica real está desativada.",
        )
    creds = await integration_hub.get_credentials(db, tenant_id, "clicksign")
    if not creds:
        raise HTTPException(
            status_code=422,
            detail="Clicksign não conectado — conecte o access token em Integrações.",
        )
    token = creds["api_token"]

    # PDF timbrado do contrato (mesmo builder do Drive/download)
    from app.utils.pdf_builder import build_petition_pdf
    pdf = build_petition_pdf(
        title=doc.titulo,
        content_html=doc.conteudo_html or doc.conteudo_texto or "",
        metadata={"status": doc.status},
        letterhead=None,
    )

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            # 1. Documento
            resp = await client.post(
                f"{_BASE}/api/v1/documents",
                params={"access_token": token},
                json={"document": {
                    "path": f"/AFJ/{(doc.titulo or 'contrato')[:60]}-{str(doc.id)[:8]}.pdf",
                    "content_base64": "data:application/pdf;base64," + base64.b64encode(pdf).decode(),
                }},
            )
            if resp.status_code >= 400:
                log.warning("clicksign_doc_error", status=resp.status_code, body=resp.text[:300])
                raise HTTPException(status_code=502, detail="Clicksign recusou o documento — confira o token em Integrações.")
            document_key = resp.json()["document"]["key"]

            # 2. Signatário (autenticação por e-mail)
            resp = await client.post(
                f"{_BASE}/api/v1/signers",
                params={"access_token": token},
                json={"signer": {
                    "email": signatario_email,
                    "name": signatario_nome,
                    "auths": ["email"],
                    "delivery": "email",
                }},
            )
            if resp.status_code >= 400:
                log.warning("clicksign_signer_error", status=resp.status_code, body=resp.text[:300])
                raise HTTPException(status_code=502, detail="Clicksign recusou o signatário — confira o e-mail informado.")
            signer_key = resp.json()["signer"]["key"]

            # 3. Vincula signatário ao documento (dispara o e-mail de assinatura)
            resp = await client.post(
                f"{_BASE}/api/v1/lists",
                params={"access_token": token},
                json={"list": {
                    "document_key": document_key,
                    "signer_key": signer_key,
                    "sign_as": "contractee",
                    "message": f"Contrato \"{doc.titulo}\" para assinatura.",
                }},
            )
            if resp.status_code >= 400:
                log.warning("clicksign_list_error", status=resp.status_code, body=resp.text[:300])
                raise HTTPException(status_code=502, detail="Clicksign não vinculou o signatário ao documento.")
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("clicksign_unreachable", error=str(exc))
        raise HTTPException(status_code=502, detail="Clicksign inalcançável — tente novamente.")

    contract.assinaturas = {
        **(contract.assinaturas or {}),
        "provider": "clicksign",
        "document_key": document_key,
        "signer_key": signer_key,
        "signer_email": signatario_email,
        "signer_nome": signatario_nome,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "signed_at": None,
    }
    contract.status = "AGUARDANDO_ASSINATURA"
    await db.flush()
    log.info("contrato_enviado_assinatura", doc=str(doc.id), document_key=document_key)
    return {"document_key": document_key, "signer_email": signatario_email}


# Eventos do Clicksign que indicam documento finalizado (todos assinaram)
_EVENTOS_FINAIS = {"auto_close", "close", "document_closed"}


async def processar_webhook_assinatura(db: AsyncSession, payload: dict) -> dict:
    """Confirma a assinatura consultando a API do Clicksign (payload = dica)."""
    event = (payload.get("event") or {}).get("name") or payload.get("event_name")
    document_key = ((payload.get("document") or {}).get("key")) or (
        ((payload.get("event") or {}).get("data") or {}).get("document", {}) or {}
    ).get("key")
    if not document_key:
        return {"processed": False, "reason": "payload sem document key"}
    if event and event not in _EVENTOS_FINAIS and event != "sign":
        return {"processed": False, "reason": f"evento ignorado ({event})"}

    # Localiza o contrato pelo document_key gravado em assinaturas
    contract = (await db.execute(
        select(Contract).where(Contract.assinaturas["document_key"].astext == document_key)
    )).scalar_one_or_none()
    if not contract:
        return {"processed": False, "reason": "contrato desconhecido para o document_key"}
    if contract.status == "ASSINADO":
        return {"processed": True, "reason": "já assinado (idempotente)"}

    doc = (await db.execute(
        select(Document).where(Document.id == contract.document_id)
    )).scalar_one_or_none()
    if not doc:
        return {"processed": False, "reason": "documento do contrato não encontrado"}

    creds = await integration_hub.get_credentials(db, doc.tenant_id, "clicksign")
    if not creds:
        return {"processed": False, "reason": "escritório sem Clicksign conectado"}

    # Verificação REAL: consultar o documento na API do Clicksign
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/api/v1/documents/{document_key}",
            params={"access_token": creds["api_token"]},
        )
    if resp.status_code >= 400:
        return {"processed": False, "reason": "documento não encontrado no Clicksign"}
    info = (resp.json() or {}).get("document") or {}
    if info.get("status") not in ("closed", "finished"):
        return {"processed": False, "reason": f"status={info.get('status')} — aguardando finalização"}

    contract.status = "ASSINADO"
    contract.assinaturas = {
        **(contract.assinaturas or {}),
        "signed_at": datetime.now(timezone.utc).isoformat(),
        "download_url": (info.get("downloads") or {}).get("signed_file_url"),
    }
    await db.flush()
    log.info("contrato_assinado_via_webhook", contract=str(contract.id), document_key=document_key)
    return {"processed": True, "reason": "contrato marcado como ASSINADO"}
