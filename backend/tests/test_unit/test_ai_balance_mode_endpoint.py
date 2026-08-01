"""Fase 137.6 — GET/PUT /me/ai-settings/balance-mode: modo de uso global
(padrao/round_robin/performance) que `byok.py::user_ai_creds()` consulta pra
decidir a ordem das IAs do usuário. `NULL` no banco == "padrao"."""
import uuid
import pytest


class _FakeDB:
    def __init__(self):
        self.executed = []
        self.committed = False

    async def execute(self, stmt):
        self.executed.append(stmt)

    async def commit(self):
        self.committed = True


class _FakeUser:
    def __init__(self, ai_balance_mode=None):
        self.id = uuid.uuid4()
        self.ai_balance_mode = ai_balance_mode


@pytest.mark.asyncio
async def test_get_devolve_padrao_quando_coluna_e_null():
    from app.api.v1.users import get_my_ai_balance_mode

    result = await get_my_ai_balance_mode(current_user=_FakeUser(ai_balance_mode=None))
    assert result == {"mode": "padrao"}


@pytest.mark.asyncio
async def test_get_devolve_o_modo_salvo():
    from app.api.v1.users import get_my_ai_balance_mode

    result = await get_my_ai_balance_mode(current_user=_FakeUser(ai_balance_mode="round_robin"))
    assert result == {"mode": "round_robin"}


@pytest.mark.asyncio
async def test_put_rejeita_modo_invalido():
    from fastapi import HTTPException
    from app.api.v1.users import update_my_ai_balance_mode, AIBalanceModeUpdate

    with pytest.raises(HTTPException) as exc:
        await update_my_ai_balance_mode(
            AIBalanceModeUpdate(mode="modo-que-nao-existe"),
            current_user=_FakeUser(), db=_FakeDB(),
        )
    assert exc.value.status_code == 422


@pytest.mark.parametrize("modo", ["padrao", "round_robin", "performance"])
@pytest.mark.asyncio
async def test_put_aceita_cada_modo_valido(modo):
    from app.api.v1.users import update_my_ai_balance_mode, AIBalanceModeUpdate

    db = _FakeDB()
    result = await update_my_ai_balance_mode(
        AIBalanceModeUpdate(mode=modo), current_user=_FakeUser(), db=db,
    )
    assert result["mode"] == modo
    assert db.committed is True
    assert len(db.executed) == 1


@pytest.mark.asyncio
async def test_put_padrao_grava_none_nao_a_string_literal():
    """`ai_balance_mode` deve voltar a NULL quando o usuário escolhe
    "padrao" de novo — nunca a string literal "padrao" no banco."""
    from app.api.v1.users import update_my_ai_balance_mode, AIBalanceModeUpdate

    db = _FakeDB()
    await update_my_ai_balance_mode(AIBalanceModeUpdate(mode="padrao"), current_user=_FakeUser(), db=db)
    sql = str(db.executed[0].compile(compile_kwargs={"literal_binds": True}))
    assert "NULL" in sql
    assert "'padrao'" not in sql


@pytest.mark.asyncio
async def test_put_round_robin_grava_a_string_no_banco():
    from app.api.v1.users import update_my_ai_balance_mode, AIBalanceModeUpdate

    db = _FakeDB()
    await update_my_ai_balance_mode(AIBalanceModeUpdate(mode="round_robin"), current_user=_FakeUser(), db=db)
    sql = str(db.executed[0].compile(compile_kwargs={"literal_binds": True}))
    assert "'round_robin'" in sql
