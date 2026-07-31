"""Serviço HITL — cria registros de aprovação e executa a ação aprovada.

Substitui a retomada por checkpoint LangGraph (que era código morto: MemorySaver
em memória, cross-process, e aresta awaiting_approval → END). O fluxo agora é
direto e testável: o executor do agente cria um Approval PENDENTE quando o grafo
sinaliza pending_approval; a resolução humana executa a ação de forma síncrona.

Invariante (CLAUDE.md): a ação crítica só ocorre após aprovação humana explícita.
"""
import uuid
import structlog

log = structlog.get_logger()


async def create_approval_from_state(db, agent_run, final_state) -> "uuid.UUID | None":
    """Cria um Approval(status=PENDENTE) se o grafo terminou aguardando aprovação.

    Usa a MESMA sessão que atualiza o AgentRun (commit é responsabilidade do caller).
    Retorna o id do Approval criado, ou None se não havia aprovação pendente.
    """
    pend = final_state.get("pending_approval") if final_state else None
    if not pend or not agent_run:
        return None

    from app.models.agent_run import Approval

    results = final_state.get("agent_results") or []
    last = results[-1] if results else None
    ai_suggestion = None
    if last is not None:
        ai_suggestion = getattr(last, "output", None) or pend
    else:
        ai_suggestion = pend

    approval = Approval(
        run_id=agent_run.id,
        tenant_id=agent_run.tenant_id,
        tipo=pend.get("tipo"),
        titulo=pend.get("titulo") or "Aprovação necessária",
        descricao=pend.get("descricao"),
        ai_suggestion=ai_suggestion,
        status="PENDENTE",
        prioridade=pend.get("prioridade", "NORMAL"),
    )
    db.add(approval)
    await db.flush()
    log.info("approval_created", run_id=str(agent_run.id), tipo=approval.tipo, approval_id=str(approval.id))
    await _notify_tenant_of_approval(db, approval)
    return approval.id


async def _notify_tenant_of_approval(db, approval) -> None:
    """Publica NEW_APPROVAL_PENDING (Fase 118) para todo colaborador do escritório
    (mesmo escopo de visibilidade de `GET /approvals` — tenant inteiro, sem
    filtro de papel; só a resolução exige ADVOGADO/SOCIO/ADMIN). Fail-soft:
    `publish_event` já não propaga erro."""
    from sqlalchemy import select
    from app.models.user import User
    from app.api.v1.ws import publish_event

    user_ids = (await db.execute(
        select(User.id).where(
            User.tenant_id == approval.tenant_id,
            User.role != "CLIENT",
            User.is_active == True,  # noqa: E712
        )
    )).scalars().all()
    for uid in user_ids:
        await publish_event(str(uid), "NEW_APPROVAL_PENDING", {
            "approval_id": str(approval.id),
            "tipo": approval.tipo,
            "titulo": approval.titulo,
            "prioridade": approval.prioridade,
        })


def _aplicar_modificacoes(doc, modifications: dict | None) -> None:
    """Fase 130 — `modifications` já era aceito pela API (`ResolveApprovalRequest`)
    mas nunca era lido: se o revisor editasse o texto na hora de aprovar, a
    edição era descartada silenciosamente e o documento ficava marcado
    APROVADO com o rascunho original (possivelmente com o problema que
    motivou a edição). Só aplica os 2 campos de conteúdo — o revisor não
    deveria conseguir mudar outros campos (client_id, tipo etc.) por essa via."""
    if not modifications:
        return
    if modifications.get("conteudo_texto"):
        doc.conteudo_texto = modifications["conteudo_texto"]
    if modifications.get("conteudo_html"):
        doc.conteudo_html = modifications["conteudo_html"]


async def execute_approved_action(db, approval, modifications: dict | None = None) -> dict:
    """Executa a ação associada a um Approval que acabou de ser APROVADO.

    Escopo estritamente por tenant. Não simula sucesso de integrações externas
    ainda não implementadas — apenas marca o artefato como aprovado/pronto.
    """
    from sqlalchemy import select
    from app.models.document import Document, Petition, Contract

    tipo = (approval.tipo or "").upper()
    sug = approval.ai_suggestion or {}
    doc_id = sug.get("document_id")

    if tipo in ("PETITION_REVIEW", "PETITION_FILING") and doc_id:
        doc = await db.get(Document, uuid.UUID(doc_id))
        if doc and doc.tenant_id == approval.tenant_id:
            _aplicar_modificacoes(doc, modifications)
            doc.status = "APROVADO"
        pet = (await db.execute(
            select(Petition).where(Petition.document_id == uuid.UUID(doc_id))
        )).scalar_one_or_none()
        if pet:
            pet.review_status = "APROVADA"
        await db.flush()
        return {"executed": "petition_approved", "document_id": doc_id,
                "note": "Petição aprovada — pronta para protocolo manual."}

    if tipo in ("CONTRACT_REVIEW", "CONTRACT_SIGN") and doc_id:
        doc = await db.get(Document, uuid.UUID(doc_id))
        if doc and doc.tenant_id == approval.tenant_id:
            _aplicar_modificacoes(doc, modifications)
            doc.status = "APROVADO"
        con = (await db.execute(
            select(Contract).where(Contract.document_id == uuid.UUID(doc_id))
        )).scalar_one_or_none()
        if con:
            con.status = "APROVADO"
        await db.flush()
        return {"executed": "contract_approved", "document_id": doc_id,
                "note": "Contrato aprovado — pronto para envio manual ao cliente."}

    # Tipos sem execução automática (ex.: CLIENT_EMAIL): registrar aprovação sem simular envio.
    return {"executed": "approved", "note": "Aprovado. Ação externa deve ser realizada manualmente."}


async def mark_rejected_action(db, approval) -> None:
    """Marca o artefato associado como rejeitado (escopo por tenant)."""
    from sqlalchemy import select
    from app.models.document import Document, Petition

    sug = approval.ai_suggestion or {}
    doc_id = sug.get("document_id")
    if not doc_id:
        return
    doc = await db.get(Document, uuid.UUID(doc_id))
    if doc and doc.tenant_id == approval.tenant_id:
        doc.status = "REJEITADO"
    pet = (await db.execute(
        select(Petition).where(Petition.document_id == uuid.UUID(doc_id))
    )).scalar_one_or_none()
    if pet:
        pet.review_status = "REJEITADA"
    await db.flush()
