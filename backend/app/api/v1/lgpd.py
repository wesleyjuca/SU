"""Endpoints LGPD — Lei Geral de Proteção de Dados (Lei 13.709/2018)."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid

from app.db.base import get_db
from app.dependencies import get_current_user, require_role
from app.models.user import User
from app.models.client import Client, ClientInteraction
from app.core.exceptions import NotFoundError
from app.core.crypto import decrypt_or_raw

router = APIRouter(prefix="/lgpd", tags=["lgpd"])


class ConsentCreate(BaseModel):
    base_legal: str
    finalidade: str
    dados_tratados: list[str]
    aceito: bool


@router.delete("/clients/{client_id}/data")
async def erase_client_data(
    client_id: str,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """
    Direito ao esquecimento (LGPD art. 18 IV) — anonimiza dados pessoais do titular.
    Operação irreversível. Registra audit trail com base legal.
    """
    result = await db.execute(
        select(Client).where(
            Client.id == uuid.UUID(client_id),
            Client.tenant_id == current_user.tenant_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise NotFoundError("Cliente", client_id)

    original_name = client.nome_completo
    client.nome_completo = f"[ANONIMIZADO-{client_id[:8]}]"
    client.razao_social = None
    client.cpf = None
    client.cnpj = None
    client.email = f"[removido]@{client_id[:8]}.invalid"
    client.telefone = None
    client.whatsapp = None
    client.observacoes = None
    client.status = "INATIVO"
    await db.flush()

    # Registra auditoria (tenant-scoped — antes nascia sem tenant_id e sumia do
    # painel de Auditoria, que filtra por tenant; e o except silencioso escondia
    # falhas numa operação sensível de LGPD).
    from app.models.audit_log import AuditLog
    db.add(AuditLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action=f"LGPD:ERASURE:{client_id}",
        success=True,
        error_detail=None,
    ))
    await db.flush()

    return {
        "message": "Dados anonimizados conforme LGPD art. 18 IV",
        "client_id": client_id,
        "titular_original": original_name[:20] + "..." if len(original_name) > 20 else original_name,
        "anonimizado_em": datetime.now(timezone.utc).isoformat(),
        "base_legal": "LGPD Lei 13.709/2018 art. 18 IV — Anonimização",
        "operador": str(current_user.id),
    }


@router.get("/clients/{client_id}/export")
async def export_client_data(
    client_id: str,
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    """Portabilidade de dados (LGPD art. 18 V) — exporta dados em formato legível.

    Restrito a ADMIN/SOCIO (mesmo padrão de erase_client_data): devolve CPF/CNPJ,
    e-mail, telefone e todo o histórico de interações do titular — um dump de PII
    não deve ser acessível a qualquer papel autenticado do tenant."""
    result = await db.execute(
        select(Client).where(
            Client.id == uuid.UUID(client_id),
            Client.tenant_id == current_user.tenant_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise NotFoundError("Cliente", client_id)

    interactions_result = await db.execute(
        select(ClientInteraction)
        .where(
            ClientInteraction.client_id == uuid.UUID(client_id),
            or_(
                ClientInteraction.tenant_id == current_user.tenant_id,
                ClientInteraction.tenant_id.is_(None),
            ),
        )
        .order_by(desc(ClientInteraction.created_at))
    )
    interactions = interactions_result.scalars().all()

    from app.models.audit_log import AuditLog
    db.add(AuditLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action=f"LGPD:EXPORT:{client_id}",
        success=True,
        error_detail=None,
    ))
    await db.flush()

    return {
        "exportado_em": datetime.now(timezone.utc).isoformat(),
        "base_legal": "LGPD Lei 13.709/2018 art. 18 V — Portabilidade de dados",
        "formato": "JSON",
        "titular": {
            "id": str(client.id),
            "nome": client.nome_completo,
            "cpf": decrypt_or_raw(client.cpf),
            "cnpj": decrypt_or_raw(client.cnpj),
            "email": client.email,
            "telefone": client.telefone,
            "whatsapp": client.whatsapp,
            "tipo": client.tipo,
            "status": client.status,
            "origem": client.origem,
            "lgpd_consent": client.lgpd_consent,
            "lgpd_consent_at": client.lgpd_consent_at.isoformat() if client.lgpd_consent_at else None,
            "criado_em": client.created_at.isoformat(),
            "atualizado_em": client.updated_at.isoformat(),
        },
        "interacoes": [
            {
                "tipo": i.tipo,
                "descricao": i.descricao,
                "created_at": i.created_at.isoformat(),
            }
            for i in interactions
        ],
    }


@router.get("/consent/{client_id}")
async def get_consent_history(
    client_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Histórico de consentimentos LGPD do titular."""
    result = await db.execute(
        select(Client).where(
            Client.id == uuid.UUID(client_id),
            Client.tenant_id == current_user.tenant_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise NotFoundError("Cliente", client_id)

    consents = []
    if client.lgpd_consent and client.lgpd_consent_at:
        consents.append({
            "tipo": "CONSENTIMENTO_INICIAL",
            "aceito": True,
            "data": client.lgpd_consent_at.isoformat(),
            "base_legal": "LGPD art. 7 I — Consentimento do titular",
        })

    return {
        "client_id": client_id,
        "nome": client.nome_completo,
        "lgpd_consent_ativo": client.lgpd_consent,
        "historico": consents,
    }


@router.post("/consent/{client_id}")
async def register_consent(
    client_id: str,
    body: ConsentCreate,
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    """Registra novo consentimento ou revogação LGPD.

    Restrito a ADMIN/SOCIO: é o registro formal usado como base legal de
    tratamento de dados perante a LGPD — não deve ser gravável por qualquer
    papel autenticado do tenant, e precisa de trilha de auditoria."""
    result = await db.execute(
        select(Client).where(
            Client.id == uuid.UUID(client_id),
            Client.tenant_id == current_user.tenant_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise NotFoundError("Cliente", client_id)

    client.lgpd_consent = body.aceito
    if body.aceito:
        client.lgpd_consent_at = datetime.now(timezone.utc)
    await db.flush()

    from app.models.audit_log import AuditLog
    db.add(AuditLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action=f"LGPD:CONSENT:{client_id}:{body.aceito}",
        success=True,
        error_detail=None,
    ))
    await db.flush()

    return {
        "client_id": client_id,
        "aceito": body.aceito,
        "base_legal": body.base_legal,
        "finalidade": body.finalidade,
        "dados_tratados": body.dados_tratados,
        "registrado_em": datetime.now(timezone.utc).isoformat(),
        "registrado_por": str(current_user.id),
    }
