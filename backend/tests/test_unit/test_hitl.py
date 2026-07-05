"""Unit tests para o serviço HITL (criação de Approval + execução aprovada)."""
import uuid
from app.services.approval_service import (
    create_approval_from_state,
    execute_approved_action,
    mark_rejected_action,
)
from app.agents.base.result import AgentResult, AgentStatus


class _FakeDBAdd:
    def __init__(self):
        self.added = []

    def add(self, o):
        self.added.append(o)

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
