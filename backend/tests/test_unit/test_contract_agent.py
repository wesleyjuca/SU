"""`ContractAgent` — o agente que EMITE o gate HITL de contrato.

Por que estes testes existem: este agente estava com cobertura zero, apesar de
ser o início de uma cadeia que termina em envio real ao Clicksign. O outro
extremo dessa cadeia (aprovação → e-sign) já tinha teste
(`test_contract_auto_esign.py`); o que faltava era justamente o passo que
produz o `approval_required` — se o `document_id` sair errado aqui, a
aprovação depois aprova o documento errado.

O LLM é mockado no próprio módulo do agente porque `call_claude` é importado
no topo de `contract_agent.py:7` (mesmo padrão de
`test_strategy_agent_playbook_fase216.py`). Nenhum teste aqui precisa de
Postgres: o agente só faz `db.add`/`db.flush`.
"""
import uuid
from decimal import Decimal

import pytest

import app.agents.contract.contract_agent as mod
from app.agents.base.result import AgentStatus
from app.agents.brain.context import AgentContext
from app.agents.contract.contract_agent import ContractAgent


class _ResultadoVazio:
    """Resposta neutra para os SELECTs de `resolve_system_prompt`."""

    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return self

    def all(self):
        return []


class _FakeDB:
    """Só o que o agente usa: `add`, `flush` e `execute` (via resolve_system_prompt)."""

    def __init__(self):
        self.adicionados = []
        self.flushes = 0

    def add(self, obj):
        self.adicionados.append(obj)

    async def flush(self):
        self.flushes += 1

    async def execute(self, *_args, **_kwargs):
        return _ResultadoVazio()

    def por_tipo(self, nome_classe: str):
        return [o for o in self.adicionados if type(o).__name__ == nome_classe]


def _mock_llm(monkeypatch, conteudo="MINUTA DE CONTRATO", prompts=None):
    async def fake_call_claude(messages, system, max_tokens=4000, temperature=0.1):
        if prompts is not None:
            prompts.append(messages[0]["content"])
        return conteudo, 120, 340, 0.031

    monkeypatch.setattr(mod, "call_claude", fake_call_claude)


async def test_sempre_pede_aprovacao_e_o_document_id_bate_com_o_output(monkeypatch):
    """O gate é o produto deste agente: ele NUNCA devolve SUCCESS.

    E o `document_id` do `approval_required` tem que ser o MESMO do `output` —
    é esse id que `execute_approved_action` usa depois para achar o documento
    a aprovar e mandar para assinatura. Divergir aqui aprovaria outro
    documento."""
    _mock_llm(monkeypatch)
    agent = ContractAgent()
    ctx = AgentContext(task_type="manage_contract", task_input={"tipo_contrato": "HONORARIOS"})

    res = await agent.execute(ctx)

    assert res.status == AgentStatus.AWAITING_APPROVAL
    assert res.needs_approval is True
    assert res.approval_required["tipo"] == "CONTRACT_REVIEW"
    assert res.approval_required["document_id"] == res.output["document_id"]
    uuid.UUID(res.output["document_id"])  # é um UUID válido, não uma string qualquer
    assert res.tokens_used == 460
    assert res.cost_usd == 0.031
    # O contexto acumula o custo para o orçamento por tenant.
    assert ctx.total_tokens == 460
    assert any(e.get("action") == "LLM_CALL" for e in ctx.audit_events)


async def test_tipo_contrato_ausente_cai_em_honorarios(monkeypatch):
    prompts = []
    _mock_llm(monkeypatch, prompts=prompts)
    agent = ContractAgent()

    res = await agent.execute(AgentContext(task_type="manage_contract", task_input={}))

    assert res.output["tipo"] == "HONORARIOS"
    assert "Honorarios" in res.approval_required["titulo"]
    assert "Honorarios" in prompts[0]


async def test_dados_vazios_nao_poluem_o_prompt(monkeypatch):
    """Campos falsy são omitidos (`if v` em contract_agent.py:36) — sem isso o
    prompt mandaria "- valor_honorarios: None" para o modelo."""
    prompts = []
    _mock_llm(monkeypatch, prompts=prompts)
    agent = ContractAgent()

    await agent.execute(AgentContext(
        task_type="manage_contract",
        task_input={"dados": {"cliente": "Fulano", "valor_honorarios": None, "observacao": ""}},
    ))

    assert "- cliente: Fulano" in prompts[0]
    assert "valor_honorarios" not in prompts[0]
    assert "observacao" not in prompts[0]


async def test_com_db_cria_document_e_contract_em_rascunho(monkeypatch):
    """Os dois registros nascem em RASCUNHO e só viram APROVADO depois do
    gate (`services/approval.py`). O `Contract.document_id` precisa apontar
    para o `Document` recém-criado — é o par que a aprovação carrega."""
    _mock_llm(monkeypatch, conteudo="CLÁUSULA PRIMEIRA — DO OBJETO")
    db = _FakeDB()
    agent = ContractAgent(db=db)
    tenant_id, client_id, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    res = await agent.execute(AgentContext(
        task_type="manage_contract", tenant_id=tenant_id, client_id=client_id, run_id=run_id,
        task_input={"tipo_contrato": "PRESTACAO_SERVICOS", "dados": {"valor_honorarios": "1500.50"}},
    ))

    docs = db.por_tipo("Document")
    contratos = db.por_tipo("Contract")
    assert len(docs) == 1 and len(contratos) == 1
    assert db.flushes == 1

    doc = docs[0]
    assert str(doc.id) == res.output["document_id"]
    assert doc.tipo == "CONTRATO"
    assert doc.status == "RASCUNHO"
    assert doc.gerado_por_ia is True
    assert doc.tenant_id == tenant_id
    assert doc.client_id == client_id
    assert doc.agent_run_id == run_id
    assert doc.conteudo_texto == "CLÁUSULA PRIMEIRA — DO OBJETO"

    contrato = contratos[0]
    assert contrato.document_id == doc.id
    assert contrato.client_id == client_id
    assert contrato.tipo == "PRESTACAO_SERVICOS"
    assert contrato.status == "RASCUNHO"
    assert contrato.valor_total == Decimal("1500.50")


@pytest.mark.parametrize("valor,esperado", [
    (None, Decimal("0")),
    (0, Decimal("0")),
    ("", Decimal("0")),
    (2500, Decimal("2500")),
])
async def test_valor_honorarios_ausente_vira_zero(monkeypatch, valor, esperado):
    """`Decimal(str(... or 0))` — o `or 0` cobre None/0/"" de uma vez."""
    _mock_llm(monkeypatch)
    db = _FakeDB()
    agent = ContractAgent(db=db)

    await agent.execute(AgentContext(
        task_type="manage_contract", task_input={"dados": {"valor_honorarios": valor}},
    ))

    assert db.por_tipo("Contract")[0].valor_total == esperado


async def test_valor_honorarios_nao_numerico_falha_em_vez_de_gravar_lixo(monkeypatch):
    """Via `run()` (não `execute()`), que é como o orquestrador chama.

    `Decimal("mil reais")` levanta `InvalidOperation`; `BaseAgent.run` tenta de
    novo (`max_retries=2`) e devolve FAILED. O importante é NÃO criar um
    contrato com valor inválido e ainda assim pedir aprovação."""
    chamadas = {"n": 0}

    async def fake_call_claude(messages, system, max_tokens=4000, temperature=0.1):
        chamadas["n"] += 1
        return "conteudo", 10, 20, 0.001

    monkeypatch.setattr(mod, "call_claude", fake_call_claude)
    db = _FakeDB()
    agent = ContractAgent(db=db)

    res = await agent.run(AgentContext(
        task_type="manage_contract", task_input={"dados": {"valor_honorarios": "mil reais"}},
    ))

    assert res.status == AgentStatus.FAILED
    assert res.error
    assert res.approval_required is None  # não pede aprovação de algo que falhou
    assert chamadas["n"] == 3  # 1 tentativa + 2 retries de BaseAgent


async def test_sem_db_o_document_id_aponta_para_documento_inexistente(monkeypatch):
    """ACHADO REGISTRADO, não corrigido nesta fase.

    O `doc_id` é gerado em `contract_agent.py:58`, ANTES e FORA do
    `if self.db:`. Sem sessão de banco, o agente devolve `AWAITING_APPROVAL`
    com um `document_id` que não corresponde a nenhum `Document` — e
    `execute_approved_action` (`services/approval.py:189-220`) faria o
    `SELECT` desse id e não acharia nada.

    Na prática o agente sempre recebe `db` no caminho real
    (`execute_chain_step` injeta a sessão), então isto é risco latente, não
    bug ativo. O teste existe para que a mudança seja consciente: se alguém
    corrigir o comportamento, este teste falha e obriga a decisão."""
    _mock_llm(monkeypatch)
    agent = ContractAgent()  # sem db

    res = await agent.execute(AgentContext(task_type="manage_contract", task_input={}))

    assert res.status == AgentStatus.AWAITING_APPROVAL
    assert res.output["document_id"]  # existe...
    assert agent.db is None  # ...mas nada foi persistido
