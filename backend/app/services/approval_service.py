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
    return approval.id


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
