"""Fase 104 — court_monitor_agent/innovation_agent: consultas de prazo/métricas
não podem vazar dado de outro tenant (mesmo padrão das Fases 95-98)."""
import uuid
import pytest

from app.agents.court_monitor.court_monitor_agent import CourtMonitorAgent
from app.agents.innovation.innovation_agent import InnovationAgent
from app.agents.brain.context import AgentContext


class _FakeScalarsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _FakeRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    """Registra a query recebida (como string) pra confirmar que o filtro de
    tenant_id está presente, sem precisar de um banco real."""
    def __init__(self, resultado):
        self._resultado = resultado
        self.queries = []

    async def execute(self, query, *_a, **_k):
        self.queries.append(str(query))
        return self._resultado


TENANT_A = uuid.uuid4()


@pytest.mark.asyncio
async def test_verificar_pautas_filtra_por_tenant_via_join():
    db = _FakeDB(_FakeScalarsResult([]))
    agent = CourtMonitorAgent(db=db)
    ctx = AgentContext(task_type="monitor_court", tenant_id=TENANT_A)

    await agent._verificar_pautas(ctx, tribunal="TJSP")

    assert len(db.queries) == 1
    sql = db.queries[0].lower()
    assert "legal_processes" in sql, "deve fazer join com legal_processes pra isolar por tenant"
    assert "tenant_id" in sql


@pytest.mark.asyncio
async def test_coletar_metricas_filtra_por_tenant():
    db = _FakeDB(_FakeRowsResult([]))
    agent = InnovationAgent(db=db)
    ctx = AgentContext(task_type="innovation_proposal", tenant_id=TENANT_A)

    await agent._coletar_metricas(ctx)

    assert len(db.queries) == 1
    sql = db.queries[0].lower()
    assert "tenant_id" in sql


@pytest.mark.asyncio
async def test_coletar_metricas_sem_db_retorna_vazio():
    agent = InnovationAgent(db=None)
    ctx = AgentContext(task_type="innovation_proposal", tenant_id=TENANT_A)
    assert await agent._coletar_metricas(ctx) == {}
