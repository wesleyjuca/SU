"""Fase 145 — corrida de TOCTOU no teto de orçamento de IA: get_budget_status()
precisa reservar custo estimado pras execuções em andamento (AgentRun com
status=RUNNING e cost_usd=NULL), senão 2 chamadas concorrentes do mesmo
usuário podem ambas ler "dentro do orçamento" e ambas prosseguir."""
import uuid

import pytest

from app.services.ai_budget import get_budget_status, RESERVA_ESTIMADA_USD_POR_RUN


class _FakeLimit:
    def __init__(self, monthly_limit_usd=10.0, alert_pct=80):
        self.monthly_limit_usd = monthly_limit_usd
        self.alert_pct = alert_pct


class _FakeResult:
    def __init__(self, scalar=None):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar


class _FakeDB:
    """Execuções na MESMA ordem de get_budget_status(): (1) AIBudgetLimit,
    (2) lock advisory (texto puro, resultado descartado), (3) soma de
    cost_usd confirmado, (4) contagem de execuções em andamento."""

    def __init__(self, limit_row, spent=0, em_andamento=0):
        self._results = [
            _FakeResult(scalar=limit_row),
            _FakeResult(scalar=None),  # pg_advisory_xact_lock
            _FakeResult(scalar=spent),
            _FakeResult(scalar=em_andamento),
        ]

    async def execute(self, query, params=None):
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_sem_limite_cadastrado_devolve_none():
    db = _FakeDB(limit_row=None)
    assert await get_budget_status(db, uuid.uuid4(), uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_gasto_confirmado_abaixo_do_teto_sem_execucoes_em_andamento_libera():
    db = _FakeDB(limit_row=_FakeLimit(monthly_limit_usd=10.0), spent=5.0, em_andamento=0)
    status = await get_budget_status(db, uuid.uuid4(), uuid.uuid4())
    assert status["spent_usd"] == 5.0
    assert status["over_limit"] is False


@pytest.mark.asyncio
async def test_execucoes_em_andamento_contam_como_reserva_e_bloqueiam():
    """A corrida real: gasto CONFIRMADO ainda abaixo do teto (US$ 9 de US$ 10),
    mas já existem 2 execuções RUNNING/cost_usd=NULL do mesmo usuário — a
    reserva (2 * US$ 1.0) empurra o total efetivo pra US$ 11, acima do teto."""
    db = _FakeDB(limit_row=_FakeLimit(monthly_limit_usd=10.0), spent=9.0, em_andamento=2)
    status = await get_budget_status(db, uuid.uuid4(), uuid.uuid4())
    assert status["over_limit"] is True
    # spent_usd exibido continua refletindo só o gasto CONFIRMADO, não a reserva.
    assert status["spent_usd"] == 9.0


@pytest.mark.asyncio
async def test_execucoes_concluidas_nao_sao_contadas_2x():
    """Uma execução já concluída (cost_usd setado) só entra na soma
    confirmada — a query de 'em_andamento' filtra cost_usd IS NULL, então
    não pode ser contada de novo como reserva."""
    db = _FakeDB(limit_row=_FakeLimit(monthly_limit_usd=10.0), spent=9.0, em_andamento=0)
    status = await get_budget_status(db, uuid.uuid4(), uuid.uuid4())
    assert status["over_limit"] is False
    assert status["spent_usd"] == 9.0


@pytest.mark.asyncio
async def test_reserva_estimada_e_um_valor_positivo_conservador():
    assert RESERVA_ESTIMADA_USD_POR_RUN > 0
