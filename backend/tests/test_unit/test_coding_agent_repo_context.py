"""Fase 106 — coding_agent ganha contexto real do repositório via repo_context
(read-only, allowlisted). Confirma que a validação de caminho bloqueia
travessia/absolutos/blocklist/fora-das-raízes, e que o agente usa o conteúdo
real quando task_input.arquivos é passado."""
import app.agents.coding.coding_agent as coding_agent_mod
from app.agents.coding.repo_context import (
    RepoContextError,
    build_contexto,
    read_arquivo,
)
from app.agents.brain.context import AgentContext
from app.agents.base.result import AgentStatus
import pytest


def test_rejeita_path_traversal():
    with pytest.raises(RepoContextError):
        read_arquivo("../../etc/passwd")


def test_rejeita_caminho_absoluto():
    with pytest.raises(RepoContextError):
        read_arquivo("/etc/passwd")


def test_rejeita_fora_das_raizes_permitidas():
    with pytest.raises(RepoContextError):
        read_arquivo("README.md")
    with pytest.raises(RepoContextError):
        read_arquivo("backend/railway.toml")


def test_rejeita_blocklist_env_e_secrets():
    with pytest.raises(RepoContextError):
        read_arquivo("backend/.env")
    with pytest.raises(RepoContextError):
        read_arquivo("backend/app/core/secrets_config.py")


def test_le_arquivo_valido_sob_backend_app():
    conteudo = read_arquivo("backend/app/agents/coding/repo_context.py")
    assert "def read_arquivo" in conteudo


def test_trunca_arquivo_grande():
    conteudo = read_arquivo("backend/app/agents/coding/repo_context.py", max_bytes=10)
    assert "[truncado" in conteudo


def test_build_contexto_tolera_erro_por_arquivo():
    resultado = build_contexto([
        "backend/app/agents/coding/repo_context.py",
        "../../etc/passwd",
    ])
    assert "def read_arquivo" in resultado
    assert "[ERRO:" in resultado


@pytest.mark.asyncio
async def test_coding_agent_usa_arquivos_do_task_input(monkeypatch):
    capturado = {}

    async def _fake_call_claude(messages, system, max_tokens=4000, temperature=0.1):
        capturado["prompt"] = messages[0]["content"]
        return "codigo gerado", 10, 20, 0.01

    monkeypatch.setattr(coding_agent_mod, "call_claude", _fake_call_claude)

    agent = coding_agent_mod.CodingAgent()
    ctx = AgentContext(
        task_type="generate_code",
        task_input={
            "descricao": "adicionar validação",
            "arquivos": ["backend/app/agents/coding/repo_context.py"],
        },
    )
    res = await agent.execute(ctx)
    assert "def read_arquivo" in capturado["prompt"]
    assert res.status == AgentStatus.AWAITING_APPROVAL


def test_coding_agent_mantem_requires_human_approval():
    assert coding_agent_mod.CodingAgent.requires_human_approval is True
