"""Fase 105 — publication_monitor_agent deve delegar a services.dje_monitor.
scan_publicacoes (a varredura real, já usada pelo job diário do Celery Beat)
em vez do antigo placeholder que sempre devolvia []."""
import uuid
import pytest

import app.services.dje_monitor as dje_monitor
from app.agents.publication_monitor.publication_monitor_agent import PublicationMonitorAgent
from app.agents.base.result import AgentStatus
from app.agents.brain.context import AgentContext

TENANT_A = uuid.uuid4()


class _FakeDB:
    """Só precisa existir (não None) — scan_publicacoes é monkeypatchado."""
    pass


@pytest.mark.asyncio
async def test_delega_para_scan_publicacoes_com_tenant_e_dias_retro(monkeypatch):
    chamadas = []

    async def _fake_scan(db, tenant_id=None, dias_retro=1):
        chamadas.append((tenant_id, dias_retro))
        return {"oabs_monitoradas": 3, "intimacoes_novas": 5, "casadas_com_processo": 2}

    monkeypatch.setattr(dje_monitor, "scan_publicacoes", _fake_scan)

    agent = PublicationMonitorAgent(db=_FakeDB())
    ctx = AgentContext(task_type="monitor_publications", tenant_id=TENANT_A, task_input={})

    res = await agent.execute(ctx)

    assert len(chamadas) == 1
    assert chamadas[0] == (TENANT_A, 1)
    assert res.status == AgentStatus.SUCCESS


@pytest.mark.asyncio
async def test_respeita_dias_retro_customizado(monkeypatch):
    chamadas = []

    async def _fake_scan(db, tenant_id=None, dias_retro=1):
        chamadas.append(dias_retro)
        return {"oabs_monitoradas": 0, "intimacoes_novas": 0, "casadas_com_processo": 0}

    monkeypatch.setattr(dje_monitor, "scan_publicacoes", _fake_scan)

    agent = PublicationMonitorAgent(db=_FakeDB())
    ctx = AgentContext(task_type="monitor_publications", tenant_id=TENANT_A, task_input={"dias_retro": 7})

    await agent.execute(ctx)
    assert chamadas == [7]


@pytest.mark.asyncio
async def test_shape_do_output_a_partir_do_resumo(monkeypatch):
    async def _fake_scan(db, tenant_id=None, dias_retro=1):
        return {"oabs_monitoradas": 4, "intimacoes_novas": 9, "casadas_com_processo": 6}

    monkeypatch.setattr(dje_monitor, "scan_publicacoes", _fake_scan)

    agent = PublicationMonitorAgent(db=_FakeDB())
    ctx = AgentContext(task_type="monitor_publications", tenant_id=TENANT_A, task_input={})

    res = await agent.execute(ctx)
    assert res.output["oabs_monitoradas"] == 4
    assert res.output["publicacoes_encontradas"] == 9
    assert res.output["intimacoes_criadas"] == 9
    assert res.output["processos_casados"] == 6


@pytest.mark.asyncio
async def test_sem_db_retorna_partial_sem_chamar_scan(monkeypatch):
    chamado = {"sim": False}

    async def _fake_scan(db, tenant_id=None, dias_retro=1):
        chamado["sim"] = True
        return {}

    monkeypatch.setattr(dje_monitor, "scan_publicacoes", _fake_scan)

    agent = PublicationMonitorAgent(db=None)
    ctx = AgentContext(task_type="monitor_publications", tenant_id=TENANT_A, task_input={})

    res = await agent.execute(ctx)
    assert res.status == AgentStatus.PARTIAL
    assert chamado["sim"] is False


@pytest.mark.asyncio
async def test_falha_no_scan_e_fail_soft(monkeypatch):
    async def _fake_scan(db, tenant_id=None, dias_retro=1):
        raise RuntimeError("Comunica indisponível")

    monkeypatch.setattr(dje_monitor, "scan_publicacoes", _fake_scan)

    agent = PublicationMonitorAgent(db=_FakeDB())
    ctx = AgentContext(task_type="monitor_publications", tenant_id=TENANT_A, task_input={})

    res = await agent.execute(ctx)
    assert res.status == AgentStatus.PARTIAL
    assert "Comunica indisponível" in res.output.get("message", "")
