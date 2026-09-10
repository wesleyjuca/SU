"""Rodada pós-260.10 (achado de auditoria, reproduzido ao vivo com fault-
injection temporária) — a checagem de `User.is_active` em `GET /ws/{user_id}`
(revogação imediata de acesso WS na desativação) estava envolta num
`except Exception: pass` que caía direto em `websocket.accept()` se a
checagem falhasse por qualquer motivo, aceitando a conexão de um usuário
já desativado. Fail-closed agora: qualquer exceção nessa checagem fecha a
conexão (`close(code=4001)`) em vez de deixar passar.

Prova nos dois sentidos: reverter pra `except Exception: pass` faz este
teste chamar `websocket.accept()` em vez de `close()` — falha imediata.
"""
import uuid

import pytest

from app.api.v1.ws import websocket_endpoint
from app.core.security import create_access_token


class _FakeWebSocket:
    def __init__(self):
        self.closed_with = None
        self.accepted = False

    async def close(self, code: int):
        self.closed_with = code

    async def accept(self):
        self.accepted = True


@pytest.mark.asyncio
async def test_is_active_check_falha_fecha_conexao_em_vez_de_aceitar(monkeypatch):
    import app.db.base as db_base_mod

    class _SessaoQuebrada:
        async def __aenter__(self):
            raise RuntimeError("falha simulada de banco durante a checagem de is_active")

        async def __aexit__(self, *exc):
            return False

    def _sessao_quebrada():
        return _SessaoQuebrada()

    monkeypatch.setattr(db_base_mod, "AsyncSessionLocal", _sessao_quebrada)

    user_id = str(uuid.uuid4())
    token = create_access_token(subject=user_id, role="ADVOGADO")
    ws = _FakeWebSocket()

    await websocket_endpoint(ws, user_id, token)

    assert ws.closed_with == 4001, (
        "a checagem de is_active falhou e a conexão deveria ter sido recusada "
        "(fail-closed) — se isto falhar, o fail-open voltou"
    )
    assert not ws.accepted, "conexão nunca deveria ser aceita quando a checagem de is_active falha"
