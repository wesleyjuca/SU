"""Guarda contra o vazamento de memória da fase pós-260.9.

Contexto: `MemorySaver()` (`langgraph.checkpoint.memory`) ficou ligado no
`get_orchestrator_graph()` por semanas depois de virar código morto —
`chain_resume.py`/`approval.py` já reconstroem a retomada de HITL a partir
de `AgentRun` desde a Fase 169.2/171, sem nunca ler o checkpoint do grafo.
Como o checkpointer nunca tinha TTL/eviction, ele guardava o estado
completo (`agent_results`, `context`) de TODO agente já disparado, para
sempre, em cada um dos 4 processos do container de produção — a causa
confirmada de um "Deploy Ran Out of Memory!" real no Railway.

Estes testes fixam o comportamento correto (sem checkpointer) e, o mais
importante, a AUSÊNCIA do símbolo — para que ninguém "conserte de volta"
reintroduzindo `MemorySaver()` sem entender por que foi removido.
"""
import inspect

import app.agents.brain.orchestrator as orch


def test_orchestrator_nao_importa_mais_memorysaver():
    """O símbolo não pode nem estar no módulo — pega reintrodução direta."""
    assert not hasattr(orch, "MemorySaver"), (
        "MemorySaver voltou a ser importado em orchestrator.py — isso é o "
        "vazamento de memória da fase pós-260.9 (Deploy Ran Out of Memory). "
        "Ver o comentário em get_orchestrator_graph() antes de reverter."
    )


def test_get_orchestrator_graph_compila_sem_checkpointer():
    """O singleton real do sistema precisa continuar com checkpointer=None."""
    orch._orchestrator_graph = None  # força reconstrução, isolado de outros testes
    try:
        graph = orch.get_orchestrator_graph()
        assert graph.checkpointer is None, (
            f"esperava checkpointer=None, achou {graph.checkpointer!r} — "
            "isso reintroduz o vazamento de memória sem TTL/eviction"
        )
    finally:
        orch._orchestrator_graph = None  # não vaza estado entre testes


def test_get_orchestrator_graph_e_singleton():
    """Continua sendo cacheado — não recompila o grafo a cada chamada."""
    orch._orchestrator_graph = None
    try:
        g1 = orch.get_orchestrator_graph()
        g2 = orch.get_orchestrator_graph()
        assert g1 is g2
    finally:
        orch._orchestrator_graph = None


async def test_ainvoke_com_thread_id_nao_quebra_sem_checkpointer():
    """Prova de execução real: `config={"configurable": {"thread_id": ...}}`
    é passado em todo call site (`agent_tasks.py`, `api/v1/agents.py`,
    `orchestration_agent.py`) — sem checkpointer, o LangGraph precisa
    aceitar isso como no-op, não levantar erro."""
    from langgraph.graph import StateGraph

    class _S(dict):
        pass

    def add_one(state):
        return {"x": state["x"] + 1}

    builder = StateGraph(dict)
    builder.add_node("add_one", add_one)
    builder.set_entry_point("add_one")
    builder.set_finish_point("add_one")
    compiled = builder.compile(checkpointer=None)

    result = await compiled.ainvoke(
        {"x": 1}, config={"configurable": {"thread_id": "prova-guarda"}}
    )
    assert result == {"x": 2}


def test_docstring_de_awaiting_approval_nao_cita_memorysaver_como_ativo():
    """A docstring do nó documenta a decisão — não pode voltar a descrever
    um MemorySaver como se estivesse configurado."""
    doc = inspect.getdoc(orch.node_awaiting_approval) or ""
    assert "MemorySaver" not in doc, (
        "a docstring voltou a citar MemorySaver como se estivesse "
        "configurado — get_orchestrator_graph() compila com checkpointer=None"
    )
    assert "checkpointer" in doc.lower()
