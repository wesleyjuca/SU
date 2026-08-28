"""Endpoints LGPD — Lei Geral de Proteção de Dados (Lei 13.709/2018)."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_, delete
from pydantic import BaseModel
from datetime import datetime, timezone
import re
import uuid

from app.db.base import get_db
from app.dependencies import get_current_user, require_role
from app.models.user import User, Session
from app.models.client import Client, ClientContact, ClientInteraction, ClientPortalAccess
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

    # Fase 228 (4ª ocorrência da mesma classe de lacuna — 176.3→210→220
    # acima) — 3 tabelas confirmadas sobrevivendo ao "esquecimento" numa
    # rodada de teste geral, cada uma reproduzida empiricamente (criar
    # cliente com CPF real → embutir nos campos abaixo → esquecer →
    # confirmar que o dado original ainda aparece).
    #
    # ProcessParty (Fase 179) tem client_id + nome/cpf_cnpj PRÓPRIOS em
    # texto puro (nunca cifrados, ao contrário de Client.cpf/cnpj) — sem
    # tenant_id próprio, escopo por join em LegalProcess (mesmo padrão de
    # _get_parte_do_tenant, processes.py). cpf_cnpj vira None (como
    # Client.cpf/cnpj), nome vira placeholder (como Client.nome_completo).
    from app.models.process import LegalProcess, ProcessParty, client_linked_processes_filter
    parties_result = await db.execute(
        select(ProcessParty)
        .join(LegalProcess, LegalProcess.id == ProcessParty.process_id)
        .where(
            ProcessParty.client_id == uuid.UUID(client_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    for party in parties_result.scalars().all():
        party.nome = f"[ANONIMIZADO-{client_id[:8]}]"
        party.cpf_cnpj = None

    # FinancialEntry.descricao e BillingInvoice.descricao/.itens são texto
    # livre que pode conter nome/CPF do titular (lançamentos e faturas de
    # honorários). valor/itens[].valor são preservados — não são PII, e
    # apagar quebraria o total de uma fatura já emitida.
    from app.models.financial import FinancialEntry, BillingInvoice
    financial_entries_result = await db.execute(
        select(FinancialEntry).where(
            FinancialEntry.client_id == uuid.UUID(client_id),
            FinancialEntry.tenant_id == current_user.tenant_id,
        )
    )
    for entry in financial_entries_result.scalars().all():
        entry.descricao = "[Conteúdo removido — LGPD art. 18 IV]"

    invoices_result = await db.execute(
        select(BillingInvoice).where(
            BillingInvoice.client_id == uuid.UUID(client_id),
            BillingInvoice.tenant_id == current_user.tenant_id,
        )
    )
    for invoice in invoices_result.scalars().all():
        if invoice.descricao:
            invoice.descricao = "[Conteúdo removido — LGPD art. 18 IV]"
        if invoice.itens:
            invoice.itens = [
                {**item, "descricao": "[Conteúdo removido — LGPD art. 18 IV]"}
                for item in invoice.itens
            ]

    # Fase 235 (rodada de teste geral) — auditoria completa de todo model
    # com `client_id` no backend, respondendo de vez a pergunta repetida
    # desde a Fase 219/228 ("vale um mecanismo estrutural pra não achar
    # tabela esquecida pela 5ª vez?"). 4 lacunas reais confirmadas:
    #
    # `User.full_name` (Fase 234) — o User técnico oculto por trás do
    # link de acesso ao portal copia o nome do titular na criação
    # (`clients.py::gerar_portal_access`) e nunca era tocado aqui — nome
    # original sobrevivia ao "esquecimento" nesse User.
    portal_users_result = await db.execute(
        select(User).where(User.linked_client_id == uuid.UUID(client_id))
    )
    for portal_user in portal_users_result.scalars().all():
        portal_user.full_name = f"[ANONIMIZADO-{client_id[:8]}]"

    # Fase 238 (achado da Fase 237) — sobrescrever `User.full_name`
    # acima nunca revogava o acesso EM SI: o `ClientPortalAccess`
    # (Fase 234) sobrevivia com `revoked_at=None`/`expires_at` intacto,
    # o `User` técnico continuava `is_active=True`, e qualquer `Session`
    # de refresh já emitida antes do esquecimento seguia válida —
    # reproduzido ao vivo que um token de portal capturado ANTES do
    # esquecimento ainda conseguia um `POST /auth/portal-redeem` NOVO
    # depois dele. Mesma lógica de `revogar_portal_access`
    # (`clients.py`) aplicada aqui: revoga o acesso, desativa o User
    # técnico e mata toda Session já emitida — fecha o canal de acesso
    # por completo, não só o nome exibido.
    access = (await db.execute(
        select(ClientPortalAccess).where(
            ClientPortalAccess.client_id == uuid.UUID(client_id),
            ClientPortalAccess.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if access and access.revoked_at is None:
        access.revoked_at = datetime.now(timezone.utc)
        portal_user_access = (await db.execute(
            select(User).where(User.id == access.portal_user_id)
        )).scalar_one_or_none()
        if portal_user_access:
            portal_user_access.is_active = False
            await db.execute(delete(Session).where(Session.user_id == portal_user_access.id))

    # `Document.conteudo_texto`/`.conteudo_html` — corpo inteiro de
    # petições/contratos gerados, quase certamente contém nome/CPF do
    # titular. `titulo`/`status`/metadados de arquivo preservados —
    # servem pro histórico do escritório, não são PII do titular.
    from app.models.document import Document, Contract
    documents_result = await db.execute(
        select(Document).where(
            Document.client_id == uuid.UUID(client_id),
            Document.tenant_id == current_user.tenant_id,
        )
    )
    documents = documents_result.scalars().all()
    for doc in documents:
        if doc.conteudo_texto:
            doc.conteudo_texto = "[Conteúdo removido — LGPD art. 18 IV]"
        if doc.conteudo_html:
            doc.conteudo_html = "[Conteúdo removido — LGPD art. 18 IV]"

    # `Contract.assinaturas` (JSONB) pode conter nome/CPF do signatário.
    # Sem tenant_id próprio — escopo pelos Document já filtrados acima.
    document_ids = [doc.id for doc in documents]
    if document_ids:
        contracts_result = await db.execute(
            select(Contract).where(Contract.document_id.in_(document_ids))
        )
        for contract in contracts_result.scalars().all():
            if contract.assinaturas:
                contract.assinaturas = None

    # `AgentRun.input_data`/`.output_data`/`.error_message` — prompts e
    # resultados de agentes de IA disparados pra esse cliente, texto
    # livre que pode conter dado pessoal. `tokens_used`/`cost_usd`/
    # `status` preservados — auditoria de custo, não PII.
    from app.models.agent_run import AgentRun
    agent_runs_result = await db.execute(
        select(AgentRun).where(
            AgentRun.client_id == uuid.UUID(client_id),
            AgentRun.tenant_id == current_user.tenant_id,
        )
    )
    for run in agent_runs_result.scalars().all():
        run.input_data = {"removido": "LGPD art. 18 IV"}
        if run.output_data:
            run.output_data = {"removido": "LGPD art. 18 IV"}
        if run.error_message:
            run.error_message = "[Conteúdo removido — LGPD art. 18 IV]"

    # `LegalProcess.descricao` — só era alcançado indiretamente via
    # ProcessParty acima; o processo em si nunca. Reaproveita
    # `client_linked_processes_filter` (Fase 222) pra cobrir os 2
    # caminhos de vínculo (client_id direto E via ProcessParty), não só
    # client_id direto.
    processes_result = await db.execute(
        select(LegalProcess).where(
            client_linked_processes_filter(uuid.UUID(client_id)),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    for process in processes_result.scalars().all():
        if process.descricao:
            process.descricao = "[Conteúdo removido — LGPD art. 18 IV]"

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

    # Fase 228 — mesmas 3 tabelas alcançadas em erase_client_data acima;
    # export mostra o dado real (roda antes de qualquer esquecimento).
    from app.models.process import LegalProcess, ProcessParty, client_linked_processes_filter
    parties_result = await db.execute(
        select(ProcessParty)
        .join(LegalProcess, LegalProcess.id == ProcessParty.process_id)
        .where(
            ProcessParty.client_id == uuid.UUID(client_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    parties = parties_result.scalars().all()

    from app.models.financial import FinancialEntry, BillingInvoice
    financial_entries_result = await db.execute(
        select(FinancialEntry).where(
            FinancialEntry.client_id == uuid.UUID(client_id),
            FinancialEntry.tenant_id == current_user.tenant_id,
        )
    )
    financial_entries = financial_entries_result.scalars().all()

    invoices_result = await db.execute(
        select(BillingInvoice).where(
            BillingInvoice.client_id == uuid.UUID(client_id),
            BillingInvoice.tenant_id == current_user.tenant_id,
        )
    )
    invoices = invoices_result.scalars().all()

    # Fase 235 — mesmas 4 lacunas fechadas acima em erase_client_data;
    # export mostra o dado real (roda antes de qualquer esquecimento).
    portal_users_result = await db.execute(
        select(User).where(User.linked_client_id == uuid.UUID(client_id))
    )
    portal_users = portal_users_result.scalars().all()

    from app.models.document import Document, Contract
    documents_result = await db.execute(
        select(Document).where(
            Document.client_id == uuid.UUID(client_id),
            Document.tenant_id == current_user.tenant_id,
        )
    )
    documents = documents_result.scalars().all()
    document_ids = [doc.id for doc in documents]
    contracts = []
    if document_ids:
        contracts_result = await db.execute(
            select(Contract).where(Contract.document_id.in_(document_ids))
        )
        contracts = contracts_result.scalars().all()

    from app.models.agent_run import AgentRun
    agent_runs_result = await db.execute(
        select(AgentRun).where(
            AgentRun.client_id == uuid.UUID(client_id),
            AgentRun.tenant_id == current_user.tenant_id,
        )
    )
    agent_runs = agent_runs_result.scalars().all()

    processes_result = await db.execute(
        select(LegalProcess).where(
            client_linked_processes_filter(uuid.UUID(client_id)),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    processes = processes_result.scalars().all()

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
        "partes_processo": [
            {
                "processo_id": str(p.process_id),
                "tipo": p.tipo,
                "nome": p.nome,
                "cpf_cnpj": p.cpf_cnpj,
                "polo": p.polo,
            }
            for p in parties
        ],
        "lancamentos_financeiros": [
            {
                "descricao": e.descricao,
                "valor": str(e.valor),
                "status": e.status,
                "data_vencimento": e.data_vencimento.isoformat() if e.data_vencimento else None,
            }
            for e in financial_entries
        ],
        "faturas": [
            {
                "numero": inv.numero,
                "descricao": inv.descricao,
                "itens": inv.itens,
                "valor_total": str(inv.valor_total) if inv.valor_total is not None else None,
                "status": inv.status,
            }
            for inv in invoices
        ],
        "acessos_portal": [
            {"user_id": str(u.id), "nome": u.full_name, "email": u.email}
            for u in portal_users
        ],
        "documentos": [
            {
                "id": str(d.id),
                "tipo": d.tipo,
                "titulo": d.titulo,
                "conteudo_texto": d.conteudo_texto,
                "status": d.status,
                "created_at": d.created_at.isoformat(),
            }
            for d in documents
        ],
        "contratos": [
            {
                "id": str(c.id),
                "tipo": c.tipo,
                "assinaturas": c.assinaturas,
                "status": c.status,
            }
            for c in contracts
        ],
        "execucoes_agentes_ia": [
            {
                "agent_name": r.agent_name,
                "input_data": r.input_data,
                "output_data": r.output_data,
                "status": r.status,
                "started_at": r.started_at.isoformat(),
            }
            for r in agent_runs
        ],
        "processos_descricao": [
            {"processo_id": str(p.id), "numero_cnj": p.numero_cnj, "descricao": p.descricao}
            for p in processes if p.descricao
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
