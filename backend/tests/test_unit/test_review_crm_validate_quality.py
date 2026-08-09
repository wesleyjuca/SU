"""Fase 107 — 3 melhorias independentes de qualidade dos agentes:
review_agent (scoring estruturado), crm_agent (persistência tenant-safe) e
os hooks validate() de visual_law_agent/marketing_agent."""
import uuid
import pytest

import app.agents.review.review_agent as review_agent_mod
import app.agents.crm.crm_agent as crm_agent_mod
import app.agents.visual_law.visual_law_agent as visual_law_mod
import app.agents.marketing.marketing_agent as marketing_mod
from app.agents.review.review_agent import ReviewAgent
from app.agents.crm.crm_agent import CRMAgent
from app.agents.visual_law.visual_law_agent import VisualLawAgent
from app.agents.marketing.marketing_agent import MarketingAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.models.client import Client, ClientInteraction

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()
CLIENT_ID = uuid.uuid4()


# ─── review_agent ────────────────────────────────────────────────────────────

def test_etapa_risco_extrai_nivel_risco_estruturado():
    parsed_json = '{"nivel_risco": "ALTO", "riscos": ["r1"], "teses_alternativas": []}'
    # simula o que _etapa_risco monta a partir do parse (mesma lógica de _parse_json_dict)
    parsed = review_agent_mod._parse_json_dict(parsed_json)
    assert parsed["nivel_risco"] == "ALTO"


def test_calcular_score_usa_nivel_risco_quando_disponivel():
    agent = ReviewAgent()
    formal = {"issues": []}
    consistencia = {"resultado": ""}
    risco = {"resultado": "texto sem menção clara", "nivel_risco": "ALTO"}
    estilo = {"resultado": ""}
    score = agent._calcular_score(formal, consistencia, risco, estilo)
    assert score == 85  # 100 - 15


def test_calcular_score_fallback_substring_quando_parse_falha():
    agent = ReviewAgent()
    formal = {"issues": []}
    consistencia = {"resultado": ""}
    risco = {"resultado": "nível de risco ALTA identificado", "nivel_risco": None}
    estilo = {"resultado": ""}
    score = agent._calcular_score(formal, consistencia, risco, estilo)
    assert score == 85  # fallback substring ainda penaliza


def test_calcular_score_usa_nota_redacao():
    agent = ReviewAgent()
    formal = {"issues": []}
    consistencia = {"resultado": ""}
    risco = {"resultado": "", "nivel_risco": "BAIXO"}
    estilo = {"resultado": "", "nota_redacao": 6}
    score = agent._calcular_score(formal, consistencia, risco, estilo)
    assert score == 94  # 100 - round((10-6)*1.5) = 100-6


# ─── crm_agent ───────────────────────────────────────────────────────────────

class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, resultados=None):
        self._resultados = list(resultados or [])
        self.added = []
        self.flush_count = 0

    async def execute(self, *_a, **_k):
        return self._resultados.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1


async def _fake_call_claude_analise(*a, **k):
    return "análise do lead: área cível, urgência média", 10, 20, 0.01


@pytest.mark.asyncio
async def test_analisar_lead_persiste_interacao_quando_ctx_client_id_presente(monkeypatch):
    monkeypatch.setattr(crm_agent_mod, "call_claude", _fake_call_claude_analise)
    db = _FakeDB()
    agent = CRMAgent(db=db)
    ctx = AgentContext(task_type="manage_crm", tenant_id=TENANT_A, client_id=CLIENT_ID,
                        task_input={"action": "analyze_lead", "nome": "Fulano", "canal": "site"})
    res = await agent.execute(ctx)
    assert res.output["persistido"] is True
    assert len(db.added) == 1
    assert isinstance(db.added[0], ClientInteraction)
    assert db.added[0].client_id == CLIENT_ID
    assert db.added[0].tipo == "SISTEMA"
    assert db.flush_count == 1


@pytest.mark.asyncio
async def test_analisar_lead_nao_persiste_quando_sem_client_id(monkeypatch):
    monkeypatch.setattr(crm_agent_mod, "call_claude", _fake_call_claude_analise)
    db = _FakeDB()
    agent = CRMAgent(db=db)
    ctx = AgentContext(task_type="manage_crm", tenant_id=TENANT_A,
                        task_input={"action": "analyze_lead", "nome": "Fulano"})
    res = await agent.execute(ctx)
    assert res.output["persistido"] is False
    assert db.added == []


@pytest.mark.asyncio
async def test_analisar_lead_client_id_de_outro_tenant_e_ignorado(monkeypatch):
    monkeypatch.setattr(crm_agent_mod, "call_claude", _fake_call_claude_analise)
    # simula: select(Client.id).where(id==cid, tenant_id==TENANT_B) não encontra
    # (o cliente pertence ao TENANT_A) -> scalar_one_or_none() -> None
    db = _FakeDB(resultados=[_FakeScalarResult(None)])
    agent = CRMAgent(db=db)
    ctx = AgentContext(task_type="manage_crm", tenant_id=TENANT_B,
                        task_input={"action": "analyze_lead", "nome": "Fulano", "client_id": str(CLIENT_ID)})
    res = await agent.execute(ctx)
    assert res.output["persistido"] is False
    assert db.added == []


@pytest.mark.asyncio
async def test_classificar_cliente_atualiza_segmento_e_observacoes(monkeypatch):
    """Fase 151 — segmento (PLATINUM/GOLD/SILVER/REGULAR) precisa ir pro campo
    Client.segmento, separado de Client.status (lifecycle:
    PROSPECTO/ATIVO/INATIVO) — antes da fase, classify_client sobrescrevia
    status direto, colidindo com o dropdown de lifecycle do frontend."""
    async def _fake_call_claude_classif(*a, **k):
        return "segmento: GOLD, frequência alta", 5, 10, 0.005

    monkeypatch.setattr(crm_agent_mod, "call_claude", _fake_call_claude_classif)
    cliente = Client(id=CLIENT_ID, tenant_id=TENANT_A, nome_completo="Cliente Teste",
                      tipo="PF", status="PROSPECTO", observacoes=None)
    db = _FakeDB(resultados=[_FakeScalarResult(cliente)])
    agent = CRMAgent(db=db)
    ctx = AgentContext(task_type="manage_crm", tenant_id=TENANT_A, client_id=CLIENT_ID,
                        task_input={"action": "classify_client", "historico": "..."})
    res = await agent.execute(ctx)
    assert res.output["persistido"] is True
    assert res.output["segmento_detectado"] == "GOLD"
    assert cliente.segmento == "GOLD"
    assert cliente.status == "PROSPECTO"  # lifecycle intocado pela classificação
    assert "GOLD" in cliente.observacoes
    assert db.flush_count == 1


# ─── validate() hooks ────────────────────────────────────────────────────────

def test_visual_law_validate_ok_para_mermaid_valido():
    agent = VisualLawAgent()
    ctx = AgentContext(task_type="visual_law_diagram")
    result = AgentResult(status=AgentStatus.SUCCESS, agent_name="visual_law_agent",
                          output={"formato": "mermaid", "mermaid": "flowchart TD\nA[Início] --> B[Fim]"})
    import asyncio
    issues = asyncio.run(agent.validate(ctx, result))
    assert issues == []


def test_visual_law_validate_detecta_mermaid_sem_tipo_reconhecido():
    agent = VisualLawAgent()
    ctx = AgentContext(task_type="visual_law_diagram")
    result = AgentResult(status=AgentStatus.SUCCESS, agent_name="visual_law_agent",
                          output={"formato": "mermaid", "mermaid": "texto qualquer sem tipo mermaid"})
    import asyncio
    issues = asyncio.run(agent.validate(ctx, result))
    assert any("tipo Mermaid reconhecido" in i for i in issues)


def test_visual_law_validate_detecta_colchetes_desbalanceados():
    agent = VisualLawAgent()
    ctx = AgentContext(task_type="visual_law_diagram")
    result = AgentResult(status=AgentStatus.SUCCESS, agent_name="visual_law_agent",
                          output={"formato": "mermaid", "mermaid": "flowchart TD\nA[Início --> B[Fim]"})
    import asyncio
    issues = asyncio.run(agent.validate(ctx, result))
    assert any("desbalanceados" in i for i in issues)


@pytest.mark.asyncio
async def test_visual_law_strict_validation_rebaixa_para_partial(monkeypatch):
    async def _fake_call_claude(*a, **k):
        return "conteúdo sem tipo mermaid reconhecido", 5, 5, 0.001

    monkeypatch.setattr(visual_law_mod, "call_claude", _fake_call_claude)
    agent = VisualLawAgent()
    ctx = AgentContext(task_type="visual_law_diagram",
                        task_input={"tipo": "fluxograma", "conteudo": "processo X", "titulo": "T"})
    res = await agent.run(ctx)
    assert res.status == AgentStatus.PARTIAL
    assert "validation_issues" in res.metadata


def test_marketing_validate_detecta_termo_proibido():
    agent = MarketingAgent()
    ctx = AgentContext(task_type="marketing_campaign")
    result = AgentResult(status=AgentStatus.AWAITING_APPROVAL, agent_name="marketing_agent",
                          output={"conteudo": "Garantimos 100% de sucesso no seu caso!"})
    import asyncio
    issues = asyncio.run(agent.validate(ctx, result))
    assert issues
    assert "Provimento 205" in issues[0]


def test_marketing_validate_ok_sem_termos_proibidos():
    agent = MarketingAgent()
    ctx = AgentContext(task_type="marketing_campaign")
    result = AgentResult(status=AgentStatus.AWAITING_APPROVAL, agent_name="marketing_agent",
                          output={"conteudo": "Conteúdo educativo sobre direito do consumidor."})
    import asyncio
    issues = asyncio.run(agent.validate(ctx, result))
    assert issues == []


@pytest.mark.asyncio
async def test_marketing_validate_nao_altera_awaiting_approval(monkeypatch):
    async def _fake_call_claude(*a, **k):
        return "Garantimos 100% de sucesso!", 5, 5, 0.001

    monkeypatch.setattr(marketing_mod, "call_claude", _fake_call_claude)
    agent = MarketingAgent()
    ctx = AgentContext(task_type="marketing_campaign",
                        task_input={"tipo": "post_instagram", "tema": "Direito do consumidor"})
    res = await agent.run(ctx)
    assert res.status == AgentStatus.AWAITING_APPROVAL
    assert "validation_issues" in res.metadata
