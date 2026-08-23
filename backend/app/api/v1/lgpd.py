"""Endpoints LGPD — Lei Geral de Proteção de Dados (Lei 13.709/2018)."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_
from pydantic import BaseModel
from datetime import datetime, timezone
import re
import uuid

from app.db.base import get_db
from app.dependencies import get_current_user, require_role
from app.models.user import User
from app.models.client import Client, ClientContact, ClientInteraction
from app.models.gov_registry_lookup import GovRegistryLookup
from app.core.exceptions import NotFoundError
from app.core.crypto import decrypt_or_raw

router = APIRouter(prefix="/lgpd", tags=["lgpd"])


class ConsentCreate(BaseModel):
    base_legal: str
    finalidade: str
    dados_tratados: list[str]
    aceito: bool


async def _lookups_do_titular(
    db: AsyncSession, tenant_id, cpf_norm: str, cnpj_norm: str,
) -> list[GovRegistryLookup]:
    """Fase 220 (achado da Fase 219) — `GovRegistryLookup.client_id`
    nunca é preenchido (só `POST /clients/validar-documento` cria
    linhas, sem esse campo), então não dá pra buscar por FK: decifra
    `documento_consultado` de cada linha do tenant e compara os dígitos
    normalizados, mesmo caminho que `GET /clients/match` (Fase 181) já
    usa pra CPF/CNPJ cifrado."""
    if not cpf_norm and not cnpj_norm:
        return []
    rows = (await db.execute(
        select(GovRegistryLookup).where(GovRegistryLookup.tenant_id == tenant_id)
    )).scalars().all()
    matches = []
    for row in rows:
        doc_norm = re.sub(r"\D", "", decrypt_or_raw(row.documento_consultado) or "")
        if doc_norm and doc_norm in (cpf_norm, cnpj_norm):
            matches.append(row)
    return matches


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
    cpf_norm = re.sub(r"\D", "", decrypt_or_raw(client.cpf) or "")
    cnpj_norm = re.sub(r"\D", "", decrypt_or_raw(client.cnpj) or "")
    client.nome_completo = f"[ANONIMIZADO-{client_id[:8]}]"
    client.razao_social = None
    client.cpf = None
    client.cnpj = None
    client.email = f"[removido]@{client_id[:8]}.invalid"
    client.telefone = None
    client.whatsapp = None
    client.observacoes = None
    client.status = "INATIVO"

    # Fase 176.3 — achado da Fase 175: o esquecimento só apagava o próprio
    # `Client`. `ClientContact` (contatos de PJ — nome/email/telefone) e
    # `ClientInteraction` (histórico livre, `descricao` pode conter PII em
    # texto — telefone citado numa ligação, nome de terceiro etc.) ficavam
    # de fora, e `GET /lgpd/clients/{id}/export` continuava devolvendo essas
    # linhas com PII completo depois do "esquecimento" — direito ao
    # esquecimento incompleto na prática.
    contacts_result = await db.execute(
        select(ClientContact).where(ClientContact.client_id == uuid.UUID(client_id))
    )
    for contact in contacts_result.scalars().all():
        contact.nome = f"[ANONIMIZADO-{client_id[:8]}]"
        contact.cargo = None
        contact.email = None
        contact.telefone = None

    interactions_result = await db.execute(
        select(ClientInteraction).where(
            ClientInteraction.client_id == uuid.UUID(client_id),
            or_(
                ClientInteraction.tenant_id == current_user.tenant_id,
                ClientInteraction.tenant_id.is_(None),
            ),
        )
    )
    for interaction in interactions_result.scalars().all():
        interaction.descricao = "[Conteúdo removido — LGPD art. 18 IV]"
        interaction.metadata_json = None

    # Fase 210 (achado da Fase 209) — mesma classe de lacuna que a Fase 176.3
    # fechou pra ClientContact/ClientInteraction: `Opportunity` (CRM, Fase
    # 161/208.2) tem `client_id` e campos de texto livre (`descricao`/
    # `motivo_perda`) que podem conter PII do titular (nome, CPF, telefone,
    # relato) — confirmado empiricamente que sobrevivia ao "esquecimento" e
    # continuava visível em GET /crm/opportunities. `titulo` não é apagado
    # de propósito: é o rótulo do negócio no funil (ex.: "Revisão
    # contratual"), não um campo que histórico mostrou conter PII.
    from app.models.crm import Opportunity
    opportunities_result = await db.execute(
        select(Opportunity).where(
            Opportunity.client_id == uuid.UUID(client_id),
            Opportunity.tenant_id == current_user.tenant_id,
        )
    )
    for opportunity in opportunities_result.scalars().all():
        if opportunity.descricao:
            opportunity.descricao = "[Conteúdo removido — LGPD art. 18 IV]"
        if opportunity.motivo_perda:
            opportunity.motivo_perda = "[Conteúdo removido — LGPD art. 18 IV]"

    # Fase 220 (achado da Fase 219) — mesma classe de lacuna que 176.3/210
    # fecharam pra ClientContact/ClientInteraction/Opportunity:
    # `GovRegistryLookup` (Fase 217, guarda CPF/CNPJ cifrado consultado
    # contra a SERPRO) sobrevivia ao "esquecimento" inteiro, decifrável.
    # Sobrescreve em vez de deletar — mesmo espírito das linhas acima.
    for lookup in await _lookups_do_titular(db, current_user.tenant_id, cpf_norm, cnpj_norm):
        lookup.documento_consultado = "[REMOVIDO-LGPD]"
        lookup.resultado_resumo = None

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

    from app.models.crm import Opportunity
    opportunities_result = await db.execute(
        select(Opportunity).where(
            Opportunity.client_id == uuid.UUID(client_id),
            Opportunity.tenant_id == current_user.tenant_id,
        )
    )
    opportunities = opportunities_result.scalars().all()

    # Fase 220 (achado da Fase 219) — mesma classe de lacuna fechada acima
    # em erase_client_data: sem isso, o titular não sabia que suas
    # consultas de validação de documento (Fase 217) também são dado
    # pessoal tratado pelo escritório.
    cpf_norm = re.sub(r"\D", "", decrypt_or_raw(client.cpf) or "")
    cnpj_norm = re.sub(r"\D", "", decrypt_or_raw(client.cnpj) or "")
    lookups = await _lookups_do_titular(db, current_user.tenant_id, cpf_norm, cnpj_norm)

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
        "oportunidades_crm": [
            {
                "titulo": o.titulo,
                "descricao": o.descricao,
                "estagio": o.estagio,
                "motivo_perda": o.motivo_perda,
                "created_at": o.created_at.isoformat(),
            }
            for o in opportunities
        ],
        "consultas_documentais": [
            {
                "tipo": lk.tipo_consulta,
                "resumo": lk.resultado_resumo,
                "consultado_em": lk.created_at.isoformat(),
            }
            for lk in lookups
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
