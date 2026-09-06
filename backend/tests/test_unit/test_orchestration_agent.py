"""`OrchestrationAgent` — o adaptador entre um `AgentContext` e o grafo.

Estava com cobertura zero. Ele traduz o resultado do grafo LangGraph em
`AgentResult`, e são exatamente essas 4 traduções (erro na invocação, erro no
state, gate pendente, sucesso) que decidem o que a API e o worker reportam.

O grafo é mockado porque `get_orchestrator_graph` é importado no topo do
módulo (`orchestration_agent.py:14`); sem isso a chamada real puxaria
Postgres, Redis, Qdrant e BYOK.
"""
import uuid

import app.agents.orchestration.orchestration_agent as mod
from app.agents.base.result import AgentStatus
from app.agents.brain.context import AgentContext
from app.agents.orchestration.orchestration_agent import OrchestrationAgent


class _GrafoFake:
    """Devolve um state pronto, ou levanta, e guarda o que recebeu."""

    def __init__(self, final_state=None, excecao=None):
        self._final_state = final_state or {}
        self._excecao = excecao
        self.chamadas = []

    async def ainvoke(self, state, config=None):
        self.chamadas.append((state, config))
        if self._excecao:
            raise self._excecao
        return {**state, **self._final_state}


def _mock_grafo(monkeypatch, **kwargs):
    grafo = _GrafoFake(**kwargs)
    monkeypatch.setattr(mod, "get_orchestrator_graph", lambda: grafo)
    return grafo


async def test_sucesso_devolve_o_final_output_do_grafo(monkeypatch):
    _mock_grafo(monkeypatch, final_state={"final_output": {"resumo": "pronto"}})
    res = await OrchestrationAgent().execute(AgentContext(task_type="qualquer"))

    assert res.status == AgentStatus.SUCCESS
    assert res.output == {"resumo": "pronto"}
    assert res.error is None


async def test_final_output_ausente_vira_dicionario_vazio_nao_none(monkeypatch):
    """`output` é sempre um dict — quem consome (`agent_tasks`, `agents.py`)
    faz `.get()` nele."""
    _mock_grafo(monkeypatch, final_state={"final_output": None})
    res = await OrchestrationAgent().execute(AgentContext(task_type="qualquer"))

    assert res.status == AgentStatus.SUCCESS
    assert res.output == {}


async def test_excecao_na_invocacao_do_grafo_vira_failed(monkeypatch):
    _mock_grafo(monkeypatch, excecao=RuntimeError("grafo explodiu"))
    res = await OrchestrationAgent().execute(AgentContext(task_type="qualquer"))

    assert res.status == AgentStatus.FAILED
    assert res.error == "grafo explodiu"
    assert res.output == {"error": "grafo explodiu"}


async def test_erro_dentro_do_state_vira_failed(monkeypatch):
    """Diferente do anterior: o grafo TERMINOU, mas com erro no state."""
    _mock_grafo(monkeypatch, final_state={"error": "agente X falhou"})
    res = await OrchestrationAgent().execute(AgentContext(task_type="qualquer"))

    assert res.status == AgentStatus.FAILED
    assert res.error == "agente X falhou"


async def test_erro_tem_precedencia_sobre_gate_pendente(monkeypatch):
    """Se o state traz os dois, o resultado é FAILED — a ordem dos `if` em
    `orchestration_agent.py:59-73` decide, e é a ordem certa: não faz sentido
    pedir aprovação de uma execução que já falhou."""
    _mock_grafo(monkeypatch, final_state={
        "error": "falhou no meio",
        "pending_approval": {"tipo": "CONTRACT_REVIEW"},
    })
    res = await OrchestrationAgent().execute(AgentContext(task_type="qualquer"))

    assert res.status == AgentStatus.FAILED
    assert res.approval_required is None


async def test_gate_pendente_propaga_o_approval_required(monkeypatch):
    """Quando o grafo para no gate, `node_post_process` NÃO roda (a aresta vai
    direto para END), então `final_output` vem `None` e o `output` sai `{}`.
    O que importa carregar adiante é o `approval_required` — é dele que
    `create_approval_from_state` monta a `Approval` no banco."""
    pendente = {"tipo": "CONTRACT_REVIEW", "titulo": "Revisar", "document_id": str(uuid.uuid4())}
    _mock_grafo(monkeypatch, final_state={"pending_approval": pendente, "final_output": None})

    res = await OrchestrationAgent().execute(AgentContext(task_type="manage_contract"))

    assert res.status == AgentStatus.AWAITING_APPROVAL
    assert res.needs_approval is True
    assert res.approval_required == pendente
    assert res.output == {}


async def test_run_id_vira_thread_id_do_grafo(monkeypatch):
    """O `thread_id` é o que dá continuidade ao checkpoint do LangGraph entre
    a pausa no gate e a retomada. Se ele não for o `run_id`, a retomada não
    encontra o estado."""
    run_id = uuid.uuid4()
    grafo = _mock_grafo(monkeypatch, final_state={"final_output": {}})

    await OrchestrationAgent().execute(AgentContext(task_type="qualquer", run_id=run_id))

    state, config = grafo.chamadas[0]
    assert config == {"configurable": {"thread_id": str(run_id)}}
    assert state["context"].run_id == run_id
    assert state["done"] is False
    assert state["agent_results"] == []


async def test_nao_exige_aprovacao_por_si(monkeypatch):
    """`requires_human_approval = False` e criticidade default: o adaptador
    nunca inventa um gate próprio — só repassa o do agente de dentro. Se isto
    mudar, toda tarefa passaria a exigir aprovação humana."""
    _mock_grafo(monkeypatch, final_state={"final_output": {"ok": True}})

    res = await OrchestrationAgent().run(AgentContext(task_type="qualquer"))

    assert res.status == AgentStatus.SUCCESS
    assert res.approval_required is None


def test_precondicoes_da_recursao_orchestration_agent():
    """ACHADO REGISTRADO, não corrigido nesta fase.

    Duas verdades do código que, juntas, formam um ciclo sem guard:

      1. `get_chain()` cai em `["orchestration_agent"]` para qualquer
         `task_type` não mapeado e sem keyword conhecida.
      2. `resolve_agent_class("orchestration_agent")` devolve esta própria
         classe.

    Ou seja: `OrchestrationAgent.execute` → grafo → `execute_chain_step` →
    `OrchestrationAgent.run` → grafo, **com o mesmo `thread_id`**. Não há
    contador de profundidade nem lista de rotas proibidas em nenhum dos dois
    arquivos.

    Este teste fixa as duas precondições — se alguém quebrar o ciclo (por
    exemplo mapeando o fallback para outro agente, ou barrando a auto-rota),
    ele falha e obriga a decisão consciente. O comportamento em runtime (se o
    LangGraph corta por recursion limit) segue **não confirmado**: provocá-lo
    de verdade exigiria rodar o grafo real, e um teste que possa entrar em
    laço infinito não tem lugar num gate de CI."""
    from app.agents.brain.orchestrator import resolve_agent_class
    from app.agents.brain.router import TASK_ROUTE_MAP, get_chain

    task_type_inexistente = "tarefa_que_ninguem_mapeou_jamais"
    assert task_type_inexistente not in TASK_ROUTE_MAP
    assert get_chain(task_type_inexistente, {}) == ["orchestration_agent"]
    assert resolve_agent_class("orchestration_agent") is OrchestrationAgent
