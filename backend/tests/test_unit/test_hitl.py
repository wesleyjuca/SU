"""Unit tests para o serviço HITL (criação de Approval + execução aprovada)."""
import uuid
from app.models.notification import Notification
from app.services.approval import (
    create_approval_from_state,
    execute_approved_action,
    mark_rejected_action,
)
from app.agents.base.result import AgentResult, AgentStatus


class _FakeScalarsEmpty:
    def scalars(self):
        class _S:
            def all(self_inner):
                return []
        return _S()

    def scalar_one_or_none(self):
        # Fase 132 — create_approval_from_state agora também consulta (mesmo
        # db.execute) se já existe uma Approval pra esse run_id antes de
        # criar; None aqui = "não existe ainda", comportamento idêntico ao
        # já testado nesta classe antes da Fase 132.
        return None


class _FakeDBAdd:
    def __init__(self):
        self.added = []

    def add(self, o):
        self.added.append(o)

    async def execute(self, stmt):
        # create_approval_from_state (Fase 118) consulta os colaboradores do
        # tenant pra notificar via WS — sem staff cadastrado aqui, no-op.
        return _FakeScalarsEmpty()

    async def flush(self):
        pass


class _FakeRun:
    def __init__(self):
        self.id = uuid.uuid4()
        self.tenant_id = uuid.uuid4()


async def test_create_approval_pending_with_scope():
    db = _FakeDBAdd()
    run = _FakeRun()
    doc_id = str(uuid.uuid4())
    res = AgentResult(
        status=AgentStatus.AWAITING_APPROVAL,
        agent_name="petition_agent",
        output={"document_id": doc_id, "conteudo": "..."},
    )
    final_state = {
        "pending_approval": {"tipo": "PETITION_REVIEW", "titulo": "Revisar", "descricao": "d"},
        "agent_results": [res],
    }
    await create_approval_from_state(db, run, final_state)
    appr = db.added[0]
    assert appr.status == "PENDENTE"
    assert appr.tipo == "PETITION_REVIEW"
    assert appr.run_id == run.id and appr.tenant_id == run.tenant_id
    assert appr.ai_suggestion["document_id"] == doc_id


async def test_no_approval_when_not_pending():
    assert await create_approval_from_state(_FakeDBAdd(), _FakeRun(), {"pending_approval": None}) is None


# ─── Fase 156 — aprovações pendentes só notificavam via WebSocket, sem
# persistência: se o revisor não estivesse com a aba aberta no exato
# momento do disparo, o alerta era perdido pra sempre. ─────────────────────

class _FakeScalarsStaff:
    def __init__(self, staff_ids):
        self._ids = staff_ids

    def scalars(self):
        ids = self._ids

        class _S:
            def all(self_inner):
                return ids
        return _S()

    def scalar_one_or_none(self):
        return None  # Fase 132 — sem Approval pré-existente pra esse run_id


class _FakeDBAddComStaff(_FakeDBAdd):
    def __init__(self, staff_ids):
        super().__init__()
        self._staff_ids = staff_ids

    async def execute(self, stmt):
        return _FakeScalarsStaff(self._staff_ids)


async def test_create_approval_persiste_notification_por_colaborador():
    staff_ids = [uuid.uuid4(), uuid.uuid4()]
    db = _FakeDBAddComStaff(staff_ids)
    run = _FakeRun()
    final_state = {
        "pending_approval": {"tipo": "PETITION_REVIEW", "titulo": "Revisar petição", "descricao": "d",
                              "prioridade": "ALTA"},
        "agent_results": [],
    }
    await create_approval_from_state(db, run, final_state)

    notifs = [o for o in db.added if isinstance(o, Notification)]
    assert len(notifs) == 2
    assert {n.user_id for n in notifs} == set(staff_ids)
    for n in notifs:
        assert n.tipo == "APROVACAO_PENDENTE"
        assert "Revisar petição" in n.titulo
        assert n.link == "/aprovacoes"
    # A Approval em si continua sendo criada normalmente (não é sobrescrita
    # pelas Notifications no mesmo db.added).
    approvals = [o for o in db.added if not isinstance(o, Notification)]
    assert len(approvals) == 1
    assert approvals[0].status == "PENDENTE"


async def test_create_approval_sem_colaboradores_nao_falha():
    """Escritório sem staff ativo (edge case) — não deve lançar, só não notifica ninguém."""
    db = _FakeDBAdd()  # scalars().all() vazio, mesma fixture já usada acima
    run = _FakeRun()
    final_state = {
        "pending_approval": {"tipo": "PETITION_REVIEW", "titulo": "Revisar", "descricao": "d"},
        "agent_results": [],
    }
    await create_approval_from_state(db, run, final_state)  # não deve lançar
    # A Approval em si ainda é criada (só não há ninguém pra notificar).
    assert any(o.status == "PENDENTE" for o in db.added if not isinstance(o, Notification))
    assert all(not isinstance(o, Notification) for o in db.added)


# ---- executor de ação aprovada ----
class _Doc:
    def __init__(self, tid):
        self.tenant_id = tid
        self.status = "RASCUNHO"


class _Pet:
    def __init__(self):
        self.review_status = "PENDENTE_REVISAO"


class _Appr:
    def __init__(self, tid, did, tipo="PETITION_REVIEW"):
        self.tipo = tipo
        self.tenant_id = tid
        self.ai_suggestion = {"document_id": did}


class _FakeDBDocs:
    def __init__(self, doc, pet):
        self._doc = doc
        self._pet = pet

    async def get(self, model, pk):
        return self._doc

    async def execute(self, stmt):
        pet = self._pet

        class _R:
            def scalar_one_or_none(self_inner):
                return pet
        return _R()

    async def flush(self):
        pass


async def test_execute_approved_petition():
    tid = uuid.uuid4()
    doc, pet = _Doc(tid), _Pet()
    out = await execute_approved_action(_FakeDBDocs(doc, pet), _Appr(tid, str(uuid.uuid4())))
    assert doc.status == "APROVADO" and pet.review_status == "APROVADA"
    assert out["executed"] == "petition_approved"


async def test_execute_respects_tenant_scope():
    # Documento de OUTRO tenant não pode ser aprovado
    doc = _Doc(uuid.uuid4())
    appr = _Appr(uuid.uuid4(), str(uuid.uuid4()))  # tenant do approval != tenant do doc
    await execute_approved_action(_FakeDBDocs(doc, _Pet()), appr)
    assert doc.status == "RASCUNHO"


async def test_mark_rejected():
    tid = uuid.uuid4()
    doc, pet = _Doc(tid), _Pet()
    await mark_rejected_action(_FakeDBDocs(doc, pet), _Appr(tid, str(uuid.uuid4())))
    assert doc.status == "REJEITADO" and pet.review_status == "REJEITADA"


# ─── Fase 130 — modifications era aceito pela API mas nunca lido: o revisor
# editava o texto na hora de aprovar e a edição sumia, documento ficava
# aprovado com o rascunho original ────────────────────────────────────────

class _DocComConteudo(_Doc):
    def __init__(self, tid):
        super().__init__(tid)
        self.conteudo_texto = "rascunho original"
        self.conteudo_html = "<p>rascunho original</p>"


async def test_execute_approved_aplica_modifications():
    tid = uuid.uuid4()
    doc, pet = _DocComConteudo(tid), _Pet()
    await execute_approved_action(
        _FakeDBDocs(doc, pet), _Appr(tid, str(uuid.uuid4())),
        modifications={"conteudo_texto": "texto corrigido pelo revisor"},
    )
    assert doc.status == "APROVADO"
    assert doc.conteudo_texto == "texto corrigido pelo revisor"
    assert doc.conteudo_html == "<p>rascunho original</p>"  # não enviado, intacto


async def test_execute_approved_sem_modifications_mantem_conteudo_original():
    tid = uuid.uuid4()
    doc, pet = _DocComConteudo(tid), _Pet()
    await execute_approved_action(_FakeDBDocs(doc, pet), _Appr(tid, str(uuid.uuid4())))
    assert doc.status == "APROVADO"
    assert doc.conteudo_texto == "rascunho original"


async def test_execute_approved_contract_aplica_modifications():
    tid = uuid.uuid4()
    doc, pet = _DocComConteudo(tid), _Pet()
    await execute_approved_action(
        _FakeDBDocs(doc, pet), _Appr(tid, str(uuid.uuid4()), tipo="CONTRACT_REVIEW"),
        modifications={"conteudo_html": "<p>cláusula corrigida</p>"},
    )
    assert doc.status == "APROVADO"
    assert doc.conteudo_html == "<p>cláusula corrigida</p>"
    assert doc.conteudo_texto == "rascunho original"  # não enviado, intacto


# ─── Fase 132 — idempotência por run_id (redelivery do Celery) ────────────
# Sem essa checagem, uma task reentregue (acks_late=True, worker cai depois
# do commit mas antes do ack) rerodava o agente do zero e criava uma 2ª
# Approval (e, pra petition_agent/contract_agent, um 2º Document) pro mesmo
# run_id lógico.

class _FakeResultComScalar:
    def __init__(self, scalar_value):
        self._scalar_value = scalar_value

    def scalar_one_or_none(self):
        return self._scalar_value

    def scalars(self):
        class _S:
            def all(self_inner):
                return []
        return _S()


class _FakeDBApprovalJaExiste(_FakeDBAdd):
    def __init__(self, existing_approval_id):
        super().__init__()
        self._existing_id = existing_approval_id

    async def execute(self, stmt):
        return _FakeResultComScalar(self._existing_id)


async def test_create_approval_from_state_idempotente_por_run_id():
    existing_id = uuid.uuid4()
    db = _FakeDBApprovalJaExiste(existing_id)
    run = _FakeRun()
    final_state = {
        "pending_approval": {"tipo": "PETITION_REVIEW", "titulo": "Revisar", "descricao": "d"},
        "agent_results": [],
    }

    result = await create_approval_from_state(db, run, final_state)

    assert result == existing_id
    assert db.added == []  # nenhuma 2ª Approval criada
