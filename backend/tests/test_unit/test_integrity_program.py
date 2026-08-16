"""Fase 189 — "Próximos passos do programa" de Ética e Integridade deixam de
ser cards estáticos: Matriz de Riscos, Treinamentos Obrigatórios e Comitê de
Integridade ganham modelos/endpoints reais, seguindo o mesmo padrão de
`ConductAcceptance`/`IntegrityReport` (Fase 4.x) já usado neste router."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.integrity import (
    RiskCreate, RiskUpdate, create_risk, update_risk, list_risks,
    TrainingCreate, TrainingUpdate, create_training, update_training,
    complete_training, list_training_completions,
    CommitteeCaseCreate, CommitteeCaseUpdate, create_committee_case, update_committee_case,
)


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar_one(self):
        return self._value


class _FakeRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return self

    def scalar_one(self):
        return self._rows[0] if self._rows else 0


class _FakeDB:
    def __init__(self, queue=None):
        self._queue = list(queue or [])
        self.added = []
        self.flushed = False

    async def execute(self, query):
        return self._queue.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed = True


class _FakeUser:
    def __init__(self, tenant_id=None, user_id=None):
        self.id = user_id or uuid.uuid4()
        self.tenant_id = tenant_id or uuid.uuid4()


# ─── Matriz de Riscos ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_create_risk_rejeita_probabilidade_invalida():
    with pytest.raises(HTTPException) as exc:
        await create_risk(
            RiskCreate(risco="x", categoria="ETICA", probabilidade="ALTISSIMA", impacto="ALTO", controles="y"),
            current_user=_FakeUser(), db=_FakeDB(),
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_create_risk_ok():
    user = _FakeUser()
    db = _FakeDB()
    result = await create_risk(
        RiskCreate(risco="Conflito de interesse não declarado", categoria="CONFLITO_INTERESSES",
                   probabilidade="MEDIA", impacto="ALTO", controles="Checklist de conflitos no intake"),
        current_user=user, db=db,
    )
    assert result["risco"] == "Conflito de interesse não declarado"
    assert db.flushed is True
    assert len(db.added) == 1
    assert db.added[0].tenant_id == user.tenant_id


@pytest.mark.asyncio
async def test_update_risk_nao_encontrado():
    with pytest.raises(HTTPException) as exc:
        await update_risk(str(uuid.uuid4()), RiskUpdate(), current_user=_FakeUser(), db=_FakeDB([_FakeScalarResult(None)]))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_risk_marcar_revisado_grava_timestamp():
    risk = SimpleNamespace(
        id=uuid.uuid4(), risco="x", categoria="ETICA", probabilidade="BAIXA", impacto="BAIXO",
        controles="c", responsavel_id=None, status="ATIVO", ultima_revisao_em=None, created_at=datetime.now(timezone.utc),
    )
    db = _FakeDB([_FakeScalarResult(risk)])
    result = await update_risk(str(risk.id), RiskUpdate(marcar_revisado=True), current_user=_FakeUser(), db=db)
    assert result["ultima_revisao_em"] is not None
    assert db.flushed is True


@pytest.mark.asyncio
async def test_update_risk_status_invalido_rejeitado():
    risk = SimpleNamespace(
        id=uuid.uuid4(), risco="x", categoria="ETICA", probabilidade="BAIXA", impacto="BAIXO",
        controles="c", responsavel_id=None, status="ATIVO", ultima_revisao_em=None, created_at=datetime.now(timezone.utc),
    )
    with pytest.raises(HTTPException) as exc:
        await update_risk(str(risk.id), RiskUpdate(status="RESOLVIDO"), current_user=_FakeUser(), db=_FakeDB([_FakeScalarResult(risk)]))
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_list_risks_expoe_nome_do_responsavel():
    tenant = uuid.uuid4()
    risk = SimpleNamespace(
        id=uuid.uuid4(), risco="x", categoria="ETICA", probabilidade="BAIXA", impacto="BAIXO",
        controles="c", responsavel_id=uuid.uuid4(), status="ATIVO", ultima_revisao_em=None, created_at=datetime.now(timezone.utc),
    )
    row = SimpleNamespace(IntegrityRisk=risk, full_name="Fulana Advogada")
    db = _FakeDB([_FakeRowsResult([row])])
    result = await list_risks(current_user=_FakeUser(tenant_id=tenant), db=db)
    assert result[0]["responsavel_nome"] == "Fulana Advogada"


# ─── Treinamentos Obrigatórios ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_create_training_rejeita_categoria_invalida():
    with pytest.raises(HTTPException) as exc:
        await create_training(
            TrainingCreate(titulo="x", categoria="MARKETING", conteudo="y"),
            current_user=_FakeUser(), db=_FakeDB(),
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_create_training_ok():
    db = _FakeDB()
    result = await create_training(
        TrainingCreate(titulo="Uso responsável de IA", categoria="USO_DE_IA", conteudo="Conteúdo da trilha"),
        current_user=_FakeUser(), db=db,
    )
    assert result["titulo"] == "Uso responsável de IA"
    assert result["obrigatorio"] is True
    assert result["concluido"] is False


@pytest.mark.asyncio
async def test_update_training_edita_campos_e_pode_desativar():
    training = SimpleNamespace(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), titulo="x", categoria="ETICA",
        conteudo="y", obrigatorio=True, ativo=True, created_at=datetime.now(timezone.utc),
    )
    db = _FakeDB([_FakeScalarResult(training)])
    result = await update_training(
        str(training.id), TrainingUpdate(titulo="Novo título", ativo=False),
        current_user=_FakeUser(), db=db,
    )
    assert result["titulo"] == "Novo título"
    assert result["ativo"] is False
    assert db.flushed is True


@pytest.mark.asyncio
async def test_update_training_nao_encontrada():
    with pytest.raises(HTTPException) as exc:
        await update_training(str(uuid.uuid4()), TrainingUpdate(), current_user=_FakeUser(), db=_FakeDB([_FakeScalarResult(None)]))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_complete_training_idempotente():
    training = SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4())
    completed_at = datetime.now(timezone.utc)
    existing = SimpleNamespace(completed_at=completed_at)
    db = _FakeDB([_FakeScalarResult(training), _FakeScalarResult(existing)])
    result = await complete_training(str(training.id), current_user=_FakeUser(), db=db)
    assert "já registrada" in result["message"].lower()
    assert db.added == []  # não duplica a conclusão


@pytest.mark.asyncio
async def test_complete_training_primeira_vez_registra():
    training = SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4())
    db = _FakeDB([_FakeScalarResult(training), _FakeScalarResult(None)])
    result = await complete_training(str(training.id), current_user=_FakeUser(), db=db)
    assert "registrada" in result["message"].lower()
    assert len(db.added) == 1


@pytest.mark.asyncio
async def test_list_training_completions_agrega_total_e_concluintes():
    training = SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4(), titulo="Ética")
    completion = SimpleNamespace(completed_at=datetime.now(timezone.utc))
    row = SimpleNamespace(IntegrityTrainingCompletion=completion, full_name="Fulano", email="fulano@afj.com.br")
    db = _FakeDB([
        _FakeScalarResult(training),
        _FakeRowsResult([5]),  # total_usuarios_ativos
        _FakeRowsResult([row]),
    ])
    result = await list_training_completions(str(training.id), current_user=_FakeUser(), db=db)
    assert result["total_usuarios_ativos"] == 5
    assert result["total_concluintes"] == 1
    assert result["concluintes"][0]["nome"] == "Fulano"


# ─── Comitê de Integridade ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_create_committee_case_sem_relato_vinculado():
    db = _FakeDB()
    result = await create_committee_case(
        CommitteeCaseCreate(titulo="Revisão de política de brindes", descricao="Deliberação anual", membros=["Sócio A"]),
        current_user=_FakeUser(), db=db,
    )
    assert result["report_id"] is None
    assert result["membros"] == ["Sócio A"]


@pytest.mark.asyncio
async def test_create_committee_case_com_relato_inexistente_404():
    db = _FakeDB([_FakeScalarResult(None)])
    with pytest.raises(HTTPException) as exc:
        await create_committee_case(
            CommitteeCaseCreate(titulo="x", descricao="y", report_id=str(uuid.uuid4())),
            current_user=_FakeUser(), db=db,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_committee_case_decidido_grava_autor_e_data():
    case = SimpleNamespace(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), report_id=None, titulo="x", descricao="y",
        status="EM_ANALISE", decisao=None, membros=[], decided_by=None, decided_at=None, created_at=datetime.now(timezone.utc),
    )
    user = _FakeUser()
    db = _FakeDB([_FakeScalarResult(case)])
    result = await update_committee_case(
        str(case.id), CommitteeCaseUpdate(status="DECIDIDO", decisao="Aprovado com ressalvas"),
        current_user=user, db=db,
    )
    assert result["status"] == "DECIDIDO"
    assert result["decisao"] == "Aprovado com ressalvas"
    assert case.decided_by == user.id
    assert case.decided_at is not None


@pytest.mark.asyncio
async def test_update_committee_case_status_invalido_rejeitado():
    case = SimpleNamespace(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), report_id=None, titulo="x", descricao="y",
        status="EM_ANALISE", decisao=None, membros=[], decided_by=None, decided_at=None, created_at=datetime.now(timezone.utc),
    )
    with pytest.raises(HTTPException) as exc:
        await update_committee_case(
            str(case.id), CommitteeCaseUpdate(status="ARQUIVADO"),
            current_user=_FakeUser(), db=_FakeDB([_FakeScalarResult(case)]),
        )
    assert exc.value.status_code == 422
