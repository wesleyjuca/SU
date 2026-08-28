"""Serviço HITL — cria registros de aprovação e executa a ação aprovada.

Substitui a retomada por checkpoint LangGraph (que era código morto: MemorySaver
em memória, cross-process, e aresta awaiting_approval → END). O fluxo agora é
direto e testável: o executor do agente cria um Approval PENDENTE quando o grafo
sinaliza pending_approval; a resolução humana executa a ação de forma síncrona.

Invariante (CLAUDE.md): a ação crítica só ocorre após aprovação humana explícita.
"""
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import HTTPException

log = structlog.get_logger()


async def create_approval_from_state(db, agent_run, final_state) -> "uuid.UUID | None":
    """Cria um Approval(status=PENDENTE) se o grafo terminou aguardando aprovação.

    Usa a MESMA sessão que atualiza o AgentRun (commit é responsabilidade do caller).
    Retorna o id do Approval criado (ou já existente — ver nota de idempotência),
    ou None se não havia aprovação pendente.
    """
    pend = final_state.get("pending_approval") if final_state else None
    if not pend or not agent_run:
        return None

    from sqlalchemy import select
    from app.models.agent_run import Approval

    # Fase 132 — idempotência por run_id: se o Celery reentregar uma task já
    # processada (acks_late=True, worker cai depois do commit mas antes do
    # ack), o agente reroda do zero (mesmo agent_run.id, já existente) e
    # chegaria aqui de novo — sem essa checagem criaria uma 2ª Approval (e,
    # no caso de petition_agent/contract_agent, um 2º Document) pro mesmo
    # gate. Fase 171 — a checagem só precisa cobrir esse cenário (o
    # redelivery só é um risco enquanto o gate atual segue PENDENTE, pois
    # é aí que reprocessar do zero recriaria a mesma Approval); por isso
    # ela é restrita a status=PENDENTE, não "qualquer Approval pra esse
    # run_id" como antes. Isso é o que permite uma chain com múltiplos
    # gates HITL: depois que o gate 1 é resolvido (APROVADO/REJEITADO),
    # ele deixa de contar como pendência em aberto e uma nova Approval
    # pro gate 2 (chamada por app/services/chain_resume.py na retomada)
    # deixa de ser barrada como "duplicata".
    existente = (await db.execute(
        select(Approval.id).where(Approval.run_id == agent_run.id, Approval.status == "PENDENTE")
    )).scalar_one_or_none()
    if existente is not None:
        log.warning("approval_ja_existe_para_run", run_id=str(agent_run.id), approval_id=str(existente))
        return existente

    results = final_state.get("agent_results") or []
    last = results[-1] if results else None
    ai_suggestion = None
    if last is not None:
        ai_suggestion = getattr(last, "output", None) or pend
    else:
        ai_suggestion = pend

    from app.config import settings

    approval = Approval(
        run_id=agent_run.id,
        tenant_id=agent_run.tenant_id,
        tipo=pend.get("tipo"),
        titulo=pend.get("titulo") or "Aprovação necessária",
        descricao=pend.get("descricao"),
        ai_suggestion=ai_suggestion,
        status="PENDENTE",
        prioridade=pend.get("prioridade", "NORMAL"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.APPROVAL_EXPIRY_DAYS),
    )
    db.add(approval)
    await db.flush()
    log.info("approval_created", run_id=str(agent_run.id), tipo=approval.tipo, approval_id=str(approval.id))
    await _notify_tenant_of_approval(db, approval)
    return approval.id


async def _notify_tenant_of_approval(db, approval) -> None:
    """Notifica todo colaborador do escritório (mesmo escopo de visibilidade de
    `GET /approvals` — tenant inteiro, sem filtro de papel; só a resolução
    exige ADVOGADO/SOCIO/ADMIN) por 2 canais complementares:

    1. `Notification` persistente (Fase 156) — sobrevive a reconexão/refresh e
       alimenta o sino de notificações (`GET /notifications`); sem isso, uma
       aprovação pendente só era vista se o revisor estivesse com a aba aberta
       no exato momento do disparo do WebSocket (a escalação de aprovações
       vencidas — `Approval.expires_at`, setado aqui, lido pelo reaper em
       `app/workers/tasks/approval_reaper.py`, Fase 191 — é um mecanismo
       separado, roda em background, não nesta notificação inicial).
       Construído inline (não via `services/notification.py::create_batch`,
       que faz seu próprio `db.commit()`) pra entrar na MESMA transação do
       `Approval` — commit é responsabilidade do caller de
       `create_approval_from_state`, mesmo contrato de sempre.
    2. Evento WS `NEW_APPROVAL_PENDING` (Fase 118), consumido por
       `useApprovals`/`useNotifications` no frontend pra atualizar o contador
       em tempo real.

    Fail-soft: `publish_event`/`publish_notification_ws` já não propagam
    erro; qualquer falha ao persistir a notificação é logada e não deve
    derrubar a criação do Approval em si (o `Approval` já foi
    `add()`+`flush()`ado pelo caller antes desta função rodar)."""
    from sqlalchemy import select
    from app.models.user import User
    from app.models.notification import Notification
    from app.services.notification import publish_notification_ws, deve_notificar
    from app.api.v1.ws import publish_event

    user_ids = (await db.execute(
        select(User.id).where(
            User.tenant_id == approval.tenant_id,
            User.role != "CLIENT",
            User.is_active == True,  # noqa: E712
        )
    )).scalars().all()
    for uid in user_ids:
        try:
            # Fase 206.2 — respeita a preferência "novas aprovações" só pra
            # este aviso de rotina; o evento NEW_APPROVAL_PENDING abaixo (que
            # alimenta o contador da fila) continua disparando sempre — a
            # fila de aprovações pendentes é uma contagem real, não deve
            # ficar defasada por uma preferência pessoal de notificação.
            if await deve_notificar(db, uid, "APROVACAO_PENDENTE"):
                notif = Notification(
                    user_id=uid,
                    tipo="APROVACAO_PENDENTE",
                    titulo=f"Aprovação pendente: {approval.titulo}",
                    corpo=approval.descricao,
                    priority=approval.prioridade,
                    link="/aprovacoes",
                )
                db.add(notif)
                await publish_notification_ws(notif)
        except Exception as exc:
            log.warning("approval_notification_persist_failed", approval_id=str(approval.id), error=str(exc))
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

        # Fase 192 — dispara a assinatura eletrônica automaticamente quando
        # dá pra fazer isso com segurança (cliente com e-mail cadastrado,
        # Clicksign conectado). Fail-soft: qualquer motivo pra não conseguir
        # deixa o contrato "aprovado, aguardando envio manual" — igual ao
        # comportamento de antes desta fase — nunca bloqueia a aprovação.
        # Protocolo automático em tribunal (PETITION_FILING) segue de fora,
        # propositalmente: o próprio cliente PJe (app/integrations/
        # tribunais/base.py) documenta isso como um "NEVER" da integração.
        auto_enviado = False
        nota = "Contrato aprovado — pronto para envio manual ao cliente."
        if doc and con and con.client_id:
            envio = await _tentar_envio_automatico_assinatura(db, approval.tenant_id, doc, con)
            if envio.get("ok"):
                auto_enviado = True
                nota = f"Contrato aprovado — enviado automaticamente para assinatura de {envio['email']} via Clicksign."
            else:
                nota = f"Contrato aprovado — pronto para envio manual ao cliente (envio automático não disparou: {envio['motivo']})."

        return {"executed": "contract_approved", "document_id": doc_id,
                "note": nota, "auto_enviado_assinatura": auto_enviado}

    if tipo == "USER_ROLE_CHANGE":
        # Fase 244 (achado do diagnóstico de cadastros) — promover alguém a
        # ADMIN/SUPERADMIN antes exigia só 1 clique de outro ADMIN, sem
        # segunda confirmação. `PUT /users/{id}` (app/api/v1/users.py) agora
        # cria este Approval em vez de aplicar direto — a mudança de role
        # real só acontece aqui, após aprovação humana explícita (mesmo
        # invariante HITL do CLAUDE.md).
        from app.models.user import User as _User

        target_user_id = sug.get("target_user_id")
        novo_role = sug.get("novo_role")
        if not target_user_id or not novo_role:
            return {"executed": "erro", "note": "Dados da solicitação incompletos."}
        target = await db.get(_User, uuid.UUID(target_user_id))
        if not target or target.tenant_id != approval.tenant_id:
            return {"executed": "erro", "note": "Usuário alvo não encontrado."}
        target.role = novo_role
        await db.flush()
        return {"executed": "role_changed", "target_user_id": target_user_id, "novo_role": novo_role,
                "note": f"Papel de {target.full_name} alterado para {novo_role}."}

    # Tipos sem execução automática (ex.: CLIENT_EMAIL): registrar aprovação sem simular envio.
    return {"executed": "approved", "note": "Aprovado. Ação externa deve ser realizada manualmente."}


async def _tentar_envio_automatico_assinatura(db, tenant_id, doc, con) -> dict:
    """Fase 192 — melhor esforço pra disparar `enviar_para_assinatura`
    (app/services/esign.py) sem intervenção humana. Nunca levanta —
    qualquer falha vira `{"ok": False, "motivo": ...}` pro caller decidir
    a mensagem, e o contrato permanece "aprovado, aguardando envio manual"."""
    from app.models.client import Client
    from app.services import integration_hub

    if not (doc.conteudo_html or doc.conteudo_texto):
        return {"ok": False, "motivo": "contrato sem conteúdo gerado"}

    client = await db.get(Client, con.client_id)
    if not client or not client.email:
        return {"ok": False, "motivo": "cliente vinculado sem e-mail cadastrado"}

    creds = await integration_hub.get_credentials(db, tenant_id, "clicksign")
    if not creds:
        return {"ok": False, "motivo": "Clicksign não conectado em Integrações"}

    try:
        from app.services.esign import enviar_para_assinatura
        resultado = await enviar_para_assinatura(db, tenant_id, doc, con, [{"email": client.email, "nome": client.nome_completo}])
        return {"ok": True, "email": client.email, **resultado}
    except HTTPException as exc:
        # Fase 199: distingue o motivo real (ex. "ambiente de demonstração")
        # do genérico "falha ao enviar" — mensagem melhor na UI de aprovação.
        return {"ok": False, "motivo": exc.detail}
    except Exception as exc:
        log.warning("contract_auto_esign_failed", document_id=str(doc.id), error=str(exc))
        return {"ok": False, "motivo": "falha ao enviar para o Clicksign"}


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
