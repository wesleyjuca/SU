"""Fase 140.2 — ADMIN propõe agentes de IA customizados, SUPERADMIN aprova.
CRUD/aprovação (mesmo padrão _FakeDB de test_agent_prompts.py), roteamento
(classify_task/_resolve_agent_class), e o executor genérico (barreira de
aprovação, teto de custo, RAG opcional)."""
import datetime
import uuid

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.custom_agent import CustomAgent
from app.api.v1.custom_agents import (
    propose_custom_agent, list_custom_agents, get_custom_agent, resolve_custom_agent,
    CustomAgentCreateRequest, CustomAgentResolveRequest,
)
from app.agents.custom.custom_agent_executor import CustomAgentExecutor
from app.agents.base.agent import BaseAgent
from app.agents.brain.context import AgentContext


class _FakeUser:
    def __init__(self, id="u1", role="ADMIN", tenant_id="t1", full_name="Fulano"):
        self.id = id
        self.role = role
        self.tenant_id = tenant_id
        self.full_name = full_name


class _FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeResult:
    def __init__(self, items=None, scalar=None):
        self._items = items or []
        self._scalar = scalar

    def scalars(self):
        return _FakeScalars(self._items)

    def scalar_one_or_none(self):
        return self._scalar


class _FakeDB:
    def __init__(self, execute_results=None, raise_on_execute=False):
        self._results = list(execute_results or [])
        self._raise = raise_on_execute
        self.added = []
        self.committed = False
        self.flushed = False

    async def execute(self, query):
        if self._raise:
            raise RuntimeError("db indisponível (simulado)")
        if self._results:
            return self._results.pop(0)
        return _FakeResult()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            if getattr(obj, "created_at", "unset") is None:
                obj.created_at = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
            if isinstance(obj, CustomAgent) and obj.max_cost_usd_per_run is None:
                obj.max_cost_usd_per_run = 0.50  # mirrors mapped_column(default=0.50), never applied outside a real flush
        self.flushed = True

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        pass


def _row(status="PENDENTE", rag_collections=None, max_cost=0.50, created_by="u1"):
    return CustomAgent(
        id=uuid.uuid4(), name="Analisador X", description="desc", system_prompt="prompt fixo",
        rag_collections=rag_collections, status=status, max_cost_usd_per_run=max_cost,
        created_by=created_by, tenant_id="t1",
        created_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        updated_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    )


# ─── Validação de payload ───────────────────────────────────────────────────

def test_create_request_rejeita_colecao_invalida():
    with pytest.raises(ValidationError):
        CustomAgentCreateRequest(
            name="X", description="d", system_prompt="p", rag_collections=["colecao_fake"],
        )


def test_create_request_aceita_colecao_valida():
    req = CustomAgentCreateRequest(name="X", description="d", system_prompt="p", rag_collections=["jurisprudencia"])
    assert req.rag_collections == ["jurisprudencia"]


# ─── POST /custom-agents ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_propose_custom_agent_cria_pendente_e_notifica_superadmins(monkeypatch):
    db = _FakeDB(execute_results=[
        _FakeResult(scalar=None),  # checagem de nome duplicado
        _FakeResult(items=["superadmin-1", "superadmin-2"]),  # select SUPERADMIN ids
    ])
    chamada = {}

    async def _fake_create_batch(db_arg, user_ids, **kwargs):
        chamada["user_ids"] = user_ids
        chamada["kwargs"] = kwargs
        return len(user_ids)

    monkeypatch.setattr("app.services.notification.create_batch", _fake_create_batch)

    body = CustomAgentCreateRequest(name="Meu Agente", description="faz X", system_prompt="Você é...")
    resp = await propose_custom_agent(body, current_user=_FakeUser(), db=db)

    assert resp.status == "PENDENTE"
    assert resp.name == "Meu Agente"
    assert chamada["user_ids"] == ["superadmin-1", "superadmin-2"]
    assert chamada["kwargs"]["tipo"] == "APROVACAO_PENDENTE"


@pytest.mark.asyncio
async def test_propose_custom_agent_nome_duplicado_409():
    db = _FakeDB(execute_results=[_FakeResult(scalar=uuid.uuid4())])
    body = CustomAgentCreateRequest(name="Já Existe", description="d", system_prompt="p")
    with pytest.raises(HTTPException) as exc_info:
        await propose_custom_agent(body, current_user=_FakeUser(), db=db)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_propose_custom_agent_sem_superadmin_nao_chama_notificacao(monkeypatch):
    db = _FakeDB(execute_results=[_FakeResult(scalar=None), _FakeResult(items=[])])
    chamou = {"sim": False}

    async def _fake_create_batch(*a, **k):
        chamou["sim"] = True

    monkeypatch.setattr("app.services.notification.create_batch", _fake_create_batch)
    body = CustomAgentCreateRequest(name="Sem Notif", description="d", system_prompt="p")
    await propose_custom_agent(body, current_user=_FakeUser(), db=db)
    assert chamou["sim"] is False


# ─── GET /custom-agents — visibilidade ──────────────────────────────────────

@pytest.mark.asyncio
async def test_list_custom_agents_admin_ve_so_os_proprios_pendentes():
    proprio = _row(status="PENDENTE", created_by="u1")
    db = _FakeDB(execute_results=[_FakeResult(items=[proprio])])
    resp = await list_custom_agents(status="PENDENTE", current_user=_FakeUser(id="u1", role="ADMIN"), db=db)
    assert len(resp) == 1


@pytest.mark.asyncio
async def test_list_custom_agents_superadmin_ve_tudo():
    outro = _row(status="PENDENTE", created_by="outro-user")
    db = _FakeDB(execute_results=[_FakeResult(items=[outro])])
    resp = await list_custom_agents(status="PENDENTE", current_user=_FakeUser(role="SUPERADMIN"), db=db)
    assert len(resp) == 1


@pytest.mark.asyncio
async def test_list_custom_agents_status_invalido_400():
    with pytest.raises(HTTPException) as exc_info:
        await list_custom_agents(status="INVALIDO", current_user=_FakeUser(), db=_FakeDB())
    assert exc_info.value.status_code == 400


# ─── POST /custom-agents/{id}/resolve ──────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_custom_agent_aprova(monkeypatch):
    row = _row(status="PENDENTE")
    db = _FakeDB(execute_results=[_FakeResult(scalar=row)])

    async def _fake_create_notification(*a, **k):
        pass

    monkeypatch.setattr("app.services.notification.create_notification", _fake_create_notification)

    body = CustomAgentResolveRequest(approved=True, max_cost_usd_per_run=1.5)
    resp = await resolve_custom_agent(str(row.id), body, current_user=_FakeUser(id="super1", role="SUPERADMIN"), db=db)

    assert resp.status == "APROVADO"
    assert resp.max_cost_usd_per_run == 1.5
    assert row.approved_by == "super1"
    assert row.approved_at is not None


@pytest.mark.asyncio
async def test_resolve_custom_agent_rejeita_grava_motivo(monkeypatch):
    row = _row(status="PENDENTE")
    db = _FakeDB(execute_results=[_FakeResult(scalar=row)])

    async def _fake_create_notification(*a, **k):
        pass

    monkeypatch.setattr("app.services.notification.create_notification", _fake_create_notification)

    body = CustomAgentResolveRequest(approved=False, rejection_reason="prompt vago demais")
    resp = await resolve_custom_agent(str(row.id), body, current_user=_FakeUser(role="SUPERADMIN"), db=db)

    assert resp.status == "REJEITADO"
    assert resp.rejection_reason == "prompt vago demais"


@pytest.mark.asyncio
async def test_resolve_custom_agent_ja_resolvido_400():
    row = _row(status="APROVADO")
    db = _FakeDB(execute_results=[_FakeResult(scalar=row)])
    body = CustomAgentResolveRequest(approved=True)
    with pytest.raises(HTTPException) as exc_info:
        await resolve_custom_agent(str(row.id), body, current_user=_FakeUser(role="SUPERADMIN"), db=db)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_get_custom_agent_inexistente_404():
    db = _FakeDB(execute_results=[_FakeResult(scalar=None)])
    with pytest.raises(HTTPException) as exc_info:
        await get_custom_agent(str(uuid.uuid4()), current_user=_FakeUser(), db=db)
    assert exc_info.value.status_code == 404


# ─── require_role("SUPERADMIN") em /resolve ────────────────────────────────

@pytest.mark.asyncio
async def test_require_role_superadmin_bloqueia_admin_comum():
    from app.dependencies import require_role
    from app.core.exceptions import ForbiddenError

    checker = require_role("SUPERADMIN")
    with pytest.raises(ForbiddenError):
        await checker(current_user=_FakeUser(role="ADMIN"))


# ─── Roteamento: classify_task + _resolve_agent_class ──────────────────────

def test_classify_task_run_custom_agent():
    from app.agents.brain.router import classify_task
    assert classify_task("run_custom_agent", {}) == "custom_agent"


def test_resolve_agent_class_custom_agent():
    from app.agents.brain.orchestrator import _resolve_agent_class
    assert _resolve_agent_class("custom_agent") is CustomAgentExecutor


# ─── CustomAgentExecutor.execute() ─────────────────────────────────────────

def _ctx(task_input=None):
    return AgentContext(task_type="run_custom_agent", task_input=task_input or {})


@pytest.mark.asyncio
async def test_executor_sem_custom_agent_id_falha():
    agent = CustomAgentExecutor(db=_FakeDB())
    result = await agent.execute(_ctx({}))
    assert result.status.value == "FAILED"
    assert "ausente" in result.error


@pytest.mark.asyncio
async def test_executor_id_invalido_falha():
    agent = CustomAgentExecutor(db=_FakeDB())
    result = await agent.execute(_ctx({"custom_agent_id": "nao-e-uuid"}))
    assert result.status.value == "FAILED"
    assert "inválido" in result.error


@pytest.mark.asyncio
async def test_executor_nao_encontrado_falha():
    db = _FakeDB(execute_results=[_FakeResult(scalar=None)])
    agent = CustomAgentExecutor(db=db)
    result = await agent.execute(_ctx({"custom_agent_id": str(uuid.uuid4())}))
    assert result.status.value == "FAILED"
    assert "não encontrado" in result.error


@pytest.mark.asyncio
async def test_executor_pendente_nao_pode_ser_disparado():
    row = _row(status="PENDENTE")
    db = _FakeDB(execute_results=[_FakeResult(scalar=row)])
    agent = CustomAgentExecutor(db=db)
    result = await agent.execute(_ctx({"custom_agent_id": str(row.id)}))
    assert result.status.value == "FAILED"
    assert "não está aprovado" in result.error


@pytest.mark.asyncio
async def test_executor_rejeitado_nao_pode_ser_disparado():
    row = _row(status="REJEITADO")
    db = _FakeDB(execute_results=[_FakeResult(scalar=row)])
    agent = CustomAgentExecutor(db=db)
    result = await agent.execute(_ctx({"custom_agent_id": str(row.id)}))
    assert result.status.value == "FAILED"
    assert "não está aprovado" in result.error


@pytest.mark.asyncio
async def test_executor_teto_de_custo_atingido_nao_chama_llm(monkeypatch):
    row = _row(status="APROVADO", max_cost=0.10)
    db = _FakeDB(execute_results=[_FakeResult(scalar=row)])
    chamou_llm = {"sim": False}

    async def _fake_call_claude(**kwargs):
        chamou_llm["sim"] = True
        return "resposta", 10, 10, 0.05

    monkeypatch.setattr("app.agents.custom.custom_agent_executor.call_claude", _fake_call_claude)

    agent = CustomAgentExecutor(db=db)
    ctx = _ctx({"custom_agent_id": str(row.id)})
    ctx.total_cost_usd = 0.10  # já no teto

    result = await agent.execute(ctx)
    assert result.status.value == "FAILED"
    assert "Cap de custo" in result.error
    assert chamou_llm["sim"] is False


@pytest.mark.asyncio
async def test_executor_aprovado_sem_rag_nao_chama_recall(monkeypatch):
    row = _row(status="APROVADO", rag_collections=None)
    db = _FakeDB(execute_results=[_FakeResult(scalar=row)])
    chamou_recall = {"sim": False}

    async def _fake_recall(self, ctx, query, collections=None, k=5):
        chamou_recall["sim"] = True
        return []

    async def _fake_call_claude(**kwargs):
        assert "system" in kwargs and kwargs["system"] == "prompt fixo"
        return "resposta do agente", 20, 30, 0.01

    monkeypatch.setattr(BaseAgent, "recall", _fake_recall)
    monkeypatch.setattr("app.agents.custom.custom_agent_executor.call_claude", _fake_call_claude)

    agent = CustomAgentExecutor(db=db)
    result = await agent.execute(_ctx({"custom_agent_id": str(row.id), "descricao": "faça isso"}))

    assert result.status.value == "SUCCESS"
    assert result.output["resposta"] == "resposta do agente"
    assert result.output["rag_chunks_usados"] == 0
    assert chamou_recall["sim"] is False


@pytest.mark.asyncio
async def test_executor_aprovado_com_rag_chama_recall_antes_do_llm(monkeypatch):
    row = _row(status="APROVADO", rag_collections=["jurisprudencia", "legislacao"])
    db = _FakeDB(execute_results=[_FakeResult(scalar=row)])
    ordem = []

    async def _fake_recall(self, ctx, query, collections=None, k=5):
        ordem.append("recall")
        assert collections == ["jurisprudencia", "legislacao"]
        return [{"text": "trecho recuperado"}]

    async def _fake_call_claude(**kwargs):
        ordem.append("call_claude")
        assert "trecho recuperado" in kwargs["messages"][0]["content"]
        return "resposta com contexto", 50, 40, 0.02

    monkeypatch.setattr(BaseAgent, "recall", _fake_recall)
    monkeypatch.setattr("app.agents.custom.custom_agent_executor.call_claude", _fake_call_claude)

    agent = CustomAgentExecutor(db=db)
    result = await agent.execute(_ctx({"custom_agent_id": str(row.id)}))

    assert result.status.value == "SUCCESS"
    assert ordem == ["recall", "call_claude"]
    assert result.output["rag_chunks_usados"] == 1
