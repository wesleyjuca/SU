"""Programa de Integridade — Código de Conduta (com aceite) e Canal de Denúncias."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, and_
from pydantic import BaseModel
import uuid
from datetime import datetime, timezone

from app.db.base import get_db
from app.dependencies import get_current_user, require_role
from app.models.user import User
from app.models.integrity import (
    ConductAcceptance, IntegrityReport,
    IntegrityRisk, IntegrityTraining, IntegrityTrainingCompletion, IntegrityCommitteeCase,
)
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/integrity", tags=["integrity"])

CATEGORIAS_DENUNCIA = ["ETICA", "CONFLITO_INTERESSES", "DADOS_LGPD", "USO_DE_IA", "ASSEDIO", "OUTROS"]

# ─── Código de Conduta ────────────────────────────────────────────────────────
# O texto/versão vive em TenantConfig.document_templates["code_of_conduct"]
# (JSONB existente — sem migração). Aceites ficam em conduct_acceptances.


async def _get_conduct(db: AsyncSession, current_user: User) -> dict:
    from app.api.v1.tenant import _get_or_create_config
    _tenant, config = await _get_or_create_config(db, current_user)
    return (config.document_templates or {}).get("code_of_conduct", {})


@router.get("/conduct")
async def get_conduct(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Código de Conduta vigente + status de aceite do usuário atual."""
    conduct = await _get_conduct(db, current_user)
    version = int(conduct.get("version") or 0)
    accepted_at = None
    if version:
        row = (await db.execute(
            select(ConductAcceptance).where(
                ConductAcceptance.user_id == current_user.id,
                ConductAcceptance.version == version,
            )
        )).scalar_one_or_none()
        accepted_at = row.accepted_at.isoformat() if row else None
    return {
        "text": conduct.get("text") or "",
        "version": version,
        "updated_at": conduct.get("updated_at"),
        "accepted": bool(accepted_at),
        "accepted_at": accepted_at,
    }


class ConductUpdate(BaseModel):
    text: str


@router.put("/conduct")
async def update_conduct(
    body: ConductUpdate,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Salva o Código de Conduta e incrementa a versão (todos precisam re-aceitar)."""
    from app.api.v1.tenant import _get_or_create_config
    from app.core.tenant import invalidate_tenant_cache, DEFAULT_TENANT_SLUG

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="O texto do código não pode ser vazio.")

    tenant, config = await _get_or_create_config(db, current_user)
    templates = dict(config.document_templates or {})
    prev = templates.get("code_of_conduct", {})
    templates["code_of_conduct"] = {
        "text": text,
        "version": int(prev.get("version") or 0) + 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    config.document_templates = templates
    await db.flush()
    await invalidate_tenant_cache(getattr(tenant, "slug", None) or DEFAULT_TENANT_SLUG)
    return {"message": "Código de Conduta publicado", "version": templates["code_of_conduct"]["version"]}


@router.post("/conduct/accept", status_code=201)
async def accept_conduct(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Registra o aceite do usuário à versão vigente do Código de Conduta."""
    conduct = await _get_conduct(db, current_user)
    version = int(conduct.get("version") or 0)
    if not version:
        raise HTTPException(status_code=422, detail="Nenhum Código de Conduta publicado ainda.")

    existing = (await db.execute(
        select(ConductAcceptance).where(
            ConductAcceptance.user_id == current_user.id,
            ConductAcceptance.version == version,
        )
    )).scalar_one_or_none()
    if existing:
        return {"message": "Aceite já registrado", "version": version}

    db.add(ConductAcceptance(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        version=version,
    ))
    await db.flush()
    return {"message": "Aceite registrado", "version": version}


@router.get("/conduct/acceptances")
async def list_acceptances(
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    """Painel do aceite: quem já aceitou a versão vigente (tenant-scoped)."""
    conduct = await _get_conduct(db, current_user)
    version = int(conduct.get("version") or 0)

    total_users = (await db.execute(
        select(func.count(User.id)).where(
            User.tenant_id == current_user.tenant_id,
            User.is_active == True,  # noqa: E712
        )
    )).scalar_one() or 0

    rows = []
    if version:
        rows = (await db.execute(
            select(ConductAcceptance, User.full_name, User.email)
            .join(User, User.id == ConductAcceptance.user_id)
            .where(
                ConductAcceptance.tenant_id == current_user.tenant_id,
                ConductAcceptance.version == version,
            )
            .order_by(desc(ConductAcceptance.accepted_at))
        )).all()

    return {
        "version": version,
        "total_usuarios_ativos": int(total_users),
        "total_aceites": len(rows),
        "aceites": [
            {"nome": r.full_name, "email": r.email, "accepted_at": r.ConductAcceptance.accepted_at.isoformat()}
            for r in rows
        ],
    }


# ─── Canal de Denúncias ───────────────────────────────────────────────────────
class ReportCreate(BaseModel):
    categoria: str
    descricao: str
    anonimo: bool = False


class ReportResolve(BaseModel):
    status: str | None = None       # ABERTO, EM_ANALISE, RESOLVIDO
    resolucao: str | None = None


def _report_to_dict(r: IntegrityReport) -> dict:
    return {
        "id": str(r.id),
        "categoria": r.categoria,
        "descricao": r.descricao,
        "anonimo": r.anonimo,
        "status": r.status,
        "resolucao": r.resolucao,
        "created_at": r.created_at.isoformat(),
    }


@router.post("/reports", status_code=201)
async def create_report(
    body: ReportCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Registra um relato. Se anônimo, o autor NÃO é gravado no banco."""
    if body.categoria not in CATEGORIAS_DENUNCIA:
        raise HTTPException(status_code=422, detail=f"Categoria inválida. Use: {', '.join(CATEGORIAS_DENUNCIA)}")
    if not body.descricao.strip():
        raise HTTPException(status_code=422, detail="Descreva o relato.")

    report = IntegrityReport(
        tenant_id=current_user.tenant_id,
        categoria=body.categoria,
        descricao=body.descricao.strip(),
        anonimo=body.anonimo,
        created_by=None if body.anonimo else current_user.id,
    )
    db.add(report)
    await db.flush()
    return {
        "id": str(report.id),
        "protocolo": str(report.id)[:8].upper(),
        "message": "Relato registrado com confidencialidade. Guarde o protocolo para acompanhamento.",
    }


@router.get("/reports")
async def list_reports(
    status: str | None = None,
    limit: int = Query(default=100, le=200),
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    """Relatos do escritório (ADMIN/SÓCIO). Autor de relato anônimo nunca é exposto."""
    query = (
        select(IntegrityReport)
        .where(IntegrityReport.tenant_id == current_user.tenant_id)
        .order_by(desc(IntegrityReport.created_at))
        .limit(limit)
    )
    if status:
        query = query.where(IntegrityReport.status == status)
    rows = (await db.execute(query)).scalars().all()
    return [_report_to_dict(r) for r in rows]


@router.put("/reports/{report_id}")
async def resolve_report(
    report_id: str,
    body: ReportResolve,
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    """Atualiza status/resolução de um relato (tenant-scoped)."""
    report = (await db.execute(
        select(IntegrityReport).where(
            IntegrityReport.id == uuid.UUID(report_id),
            IntegrityReport.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if not report:
        raise NotFoundError("Relato", report_id)

    if body.status:
        if body.status not in ("ABERTO", "EM_ANALISE", "RESOLVIDO"):
            raise HTTPException(status_code=422, detail="Status inválido (ABERTO | EM_ANALISE | RESOLVIDO)")
        report.status = body.status
        if body.status == "RESOLVIDO":
            report.resolved_by = current_user.id
    if body.resolucao is not None:
        report.resolucao = body.resolucao.strip() or None
    await db.flush()
    return _report_to_dict(report)


# ─── Matriz de Riscos de Integridade — Fase 189.1 ─────────────────────────────
PROBABILIDADES = ["BAIXA", "MEDIA", "ALTA"]
IMPACTOS = ["BAIXO", "MEDIO", "ALTO"]
STATUS_RISCO = ["ATIVO", "MITIGADO", "ENCERRADO"]


class RiskCreate(BaseModel):
    risco: str
    categoria: str
    probabilidade: str
    impacto: str
    controles: str
    responsavel_id: str | None = None


class RiskUpdate(BaseModel):
    risco: str | None = None
    categoria: str | None = None
    probabilidade: str | None = None
    impacto: str | None = None
    controles: str | None = None
    responsavel_id: str | None = None
    status: str | None = None
    marcar_revisado: bool = False


async def _validar_responsavel_id(db: AsyncSession, responsavel_id: str | None, tenant_id) -> uuid.UUID | None:
    """Garante que o responsavel_id (se informado) pertence ao tenant — mesmo
    padrão de `_validar_client_id`/`_validar_process_id` (documents.py).

    Fase 204 (achado MÉDIO da Fase 203) — antes, `responsavel_id` era gravado
    sem checar o tenant, e `list_risks()` fazia um outer join sem filtro de
    tenant no lado de `User` — um ADMIN podia setar `responsavel_id` pra um
    UUID de usuário de outro escritório (se soubesse/adivinhasse) e ler de
    volta o `full_name` desse usuário via GET /integrity/risks."""
    if not responsavel_id:
        return None
    rid = uuid.UUID(responsavel_id)
    existe = (await db.execute(
        select(User.id).where(User.id == rid, User.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not existe:
        raise HTTPException(status_code=422, detail="Responsável não encontrado neste escritório.")
    return rid


def _risk_to_dict(r: IntegrityRisk, nome_responsavel: str | None = None) -> dict:
    return {
        "id": str(r.id),
        "risco": r.risco,
        "categoria": r.categoria,
        "probabilidade": r.probabilidade,
        "impacto": r.impacto,
        "controles": r.controles,
        "responsavel_id": str(r.responsavel_id) if r.responsavel_id else None,
        "responsavel_nome": nome_responsavel,
        "status": r.status,
        "ultima_revisao_em": r.ultima_revisao_em.isoformat() if r.ultima_revisao_em else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/risks")
async def list_risks(
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(IntegrityRisk, User.full_name)
        .outerjoin(User, and_(User.id == IntegrityRisk.responsavel_id, User.tenant_id == current_user.tenant_id))
        .where(IntegrityRisk.tenant_id == current_user.tenant_id)
        .order_by(desc(IntegrityRisk.created_at))
    )).all()
    return [_risk_to_dict(r.IntegrityRisk, r.full_name) for r in rows]


@router.post("/risks", status_code=201)
async def create_risk(
    body: RiskCreate,
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    if body.probabilidade not in PROBABILIDADES:
        raise HTTPException(status_code=422, detail=f"Probabilidade inválida. Use: {', '.join(PROBABILIDADES)}")
    if body.impacto not in IMPACTOS:
        raise HTTPException(status_code=422, detail=f"Impacto inválido. Use: {', '.join(IMPACTOS)}")
    if not body.risco.strip() or not body.controles.strip():
        raise HTTPException(status_code=422, detail="Informe o risco e os controles.")

    responsavel_id = await _validar_responsavel_id(db, body.responsavel_id, current_user.tenant_id)
    risk = IntegrityRisk(
        tenant_id=current_user.tenant_id,
        risco=body.risco.strip(),
        categoria=body.categoria,
        probabilidade=body.probabilidade,
        impacto=body.impacto,
        controles=body.controles.strip(),
        responsavel_id=responsavel_id,
        created_by=current_user.id,
    )
    db.add(risk)
    await db.flush()
    return _risk_to_dict(risk)


@router.put("/risks/{risk_id}")
async def update_risk(
    risk_id: str,
    body: RiskUpdate,
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    risk = (await db.execute(
        select(IntegrityRisk).where(
            IntegrityRisk.id == uuid.UUID(risk_id),
            IntegrityRisk.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if not risk:
        raise NotFoundError("Risco", risk_id)

    if body.probabilidade is not None and body.probabilidade not in PROBABILIDADES:
        raise HTTPException(status_code=422, detail=f"Probabilidade inválida. Use: {', '.join(PROBABILIDADES)}")
    if body.impacto is not None and body.impacto not in IMPACTOS:
        raise HTTPException(status_code=422, detail=f"Impacto inválido. Use: {', '.join(IMPACTOS)}")
    if body.status is not None and body.status not in STATUS_RISCO:
        raise HTTPException(status_code=422, detail=f"Status inválido. Use: {', '.join(STATUS_RISCO)}")

    if body.risco is not None:
        risk.risco = body.risco.strip()
    if body.categoria is not None:
        risk.categoria = body.categoria
    if body.probabilidade is not None:
        risk.probabilidade = body.probabilidade
    if body.impacto is not None:
        risk.impacto = body.impacto
    if body.controles is not None:
        risk.controles = body.controles.strip()
    if body.responsavel_id is not None:
        risk.responsavel_id = await _validar_responsavel_id(db, body.responsavel_id, current_user.tenant_id)
    if body.status is not None:
        risk.status = body.status
    if body.marcar_revisado:
        risk.ultima_revisao_em = datetime.now(timezone.utc)
    await db.flush()
    return _risk_to_dict(risk)


# ─── Treinamentos Obrigatórios — Fase 189.2 ───────────────────────────────────
CATEGORIAS_TREINAMENTO = ["ETICA", "LGPD", "USO_DE_IA"]


class TrainingCreate(BaseModel):
    titulo: str
    categoria: str
    conteudo: str
    obrigatorio: bool = True


class TrainingUpdate(BaseModel):
    titulo: str | None = None
    categoria: str | None = None
    conteudo: str | None = None
    obrigatorio: bool | None = None
    ativo: bool | None = None


def _training_to_dict(t: IntegrityTraining, concluido: bool = False, concluido_em: str | None = None) -> dict:
    return {
        "id": str(t.id),
        "titulo": t.titulo,
        "categoria": t.categoria,
        "conteudo": t.conteudo,
        "obrigatorio": t.obrigatorio,
        "ativo": t.ativo,
        "concluido": concluido,
        "concluido_em": concluido_em,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@router.get("/trainings")
async def list_trainings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trilhas ativas do escritório + status de conclusão do usuário atual."""
    trilhas = (await db.execute(
        select(IntegrityTraining)
        .where(IntegrityTraining.tenant_id == current_user.tenant_id, IntegrityTraining.ativo == True)  # noqa: E712
        .order_by(desc(IntegrityTraining.created_at))
    )).scalars().all()

    concluidas = {}
    if trilhas:
        rows = (await db.execute(
            select(IntegrityTrainingCompletion).where(
                IntegrityTrainingCompletion.user_id == current_user.id,
                IntegrityTrainingCompletion.training_id.in_([t.id for t in trilhas]),
            )
        )).scalars().all()
        concluidas = {c.training_id: c.completed_at for c in rows}

    return [
        _training_to_dict(t, concluido=t.id in concluidas, concluido_em=concluidas[t.id].isoformat() if t.id in concluidas else None)
        for t in trilhas
    ]


@router.post("/trainings", status_code=201)
async def create_training(
    body: TrainingCreate,
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    if body.categoria not in CATEGORIAS_TREINAMENTO:
        raise HTTPException(status_code=422, detail=f"Categoria inválida. Use: {', '.join(CATEGORIAS_TREINAMENTO)}")
    if not body.titulo.strip() or not body.conteudo.strip():
        raise HTTPException(status_code=422, detail="Informe o título e o conteúdo da trilha.")

    training = IntegrityTraining(
        tenant_id=current_user.tenant_id,
        titulo=body.titulo.strip(),
        categoria=body.categoria,
        conteudo=body.conteudo.strip(),
        obrigatorio=body.obrigatorio,
        created_by=current_user.id,
    )
    db.add(training)
    await db.flush()
    return _training_to_dict(training)


@router.put("/trainings/{training_id}")
async def update_training(
    training_id: str,
    body: TrainingUpdate,
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    training = (await db.execute(
        select(IntegrityTraining).where(
            IntegrityTraining.id == uuid.UUID(training_id),
            IntegrityTraining.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if not training:
        raise NotFoundError("Trilha", training_id)

    if body.categoria is not None and body.categoria not in CATEGORIAS_TREINAMENTO:
        raise HTTPException(status_code=422, detail=f"Categoria inválida. Use: {', '.join(CATEGORIAS_TREINAMENTO)}")

    if body.titulo is not None:
        training.titulo = body.titulo.strip()
    if body.categoria is not None:
        training.categoria = body.categoria
    if body.conteudo is not None:
        training.conteudo = body.conteudo.strip()
    if body.obrigatorio is not None:
        training.obrigatorio = body.obrigatorio
    if body.ativo is not None:
        training.ativo = body.ativo
    await db.flush()
    return _training_to_dict(training)


@router.post("/trainings/{training_id}/complete", status_code=201)
async def complete_training(
    training_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Registra a conclusão da trilha pelo usuário atual (idempotente)."""
    training = (await db.execute(
        select(IntegrityTraining).where(
            IntegrityTraining.id == uuid.UUID(training_id),
            IntegrityTraining.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if not training:
        raise NotFoundError("Trilha", training_id)

    existing = (await db.execute(
        select(IntegrityTrainingCompletion).where(
            IntegrityTrainingCompletion.user_id == current_user.id,
            IntegrityTrainingCompletion.training_id == training.id,
        )
    )).scalar_one_or_none()
    if existing:
        return {"message": "Conclusão já registrada", "concluido_em": existing.completed_at.isoformat()}

    completion = IntegrityTrainingCompletion(
        training_id=training.id, user_id=current_user.id, tenant_id=current_user.tenant_id,
    )
    db.add(completion)
    await db.flush()
    concluido_em = completion.completed_at.isoformat() if completion.completed_at else datetime.now(timezone.utc).isoformat()
    return {"message": "Conclusão registrada", "concluido_em": concluido_em}


@router.get("/trainings/{training_id}/completions")
async def list_training_completions(
    training_id: str,
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    """Painel do gestor: % da equipe que já concluiu a trilha (tenant-scoped)."""
    training = (await db.execute(
        select(IntegrityTraining).where(
            IntegrityTraining.id == uuid.UUID(training_id),
            IntegrityTraining.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if not training:
        raise NotFoundError("Trilha", training_id)

    total_users = (await db.execute(
        select(func.count(User.id)).where(
            User.tenant_id == current_user.tenant_id,
            User.is_active == True,  # noqa: E712
        )
    )).scalar_one() or 0

    rows = (await db.execute(
        select(IntegrityTrainingCompletion, User.full_name, User.email)
        .join(User, User.id == IntegrityTrainingCompletion.user_id)
        .where(IntegrityTrainingCompletion.training_id == training.id)
        .order_by(desc(IntegrityTrainingCompletion.completed_at))
    )).all()

    return {
        "titulo": training.titulo,
        "total_usuarios_ativos": int(total_users),
        "total_concluintes": len(rows),
        "concluintes": [
            {"nome": r.full_name, "email": r.email, "completed_at": r.IntegrityTrainingCompletion.completed_at.isoformat()}
            for r in rows
        ],
    }


# ─── Comitê de Integridade — Fase 189.3 ───────────────────────────────────────
STATUS_CASO = ["EM_ANALISE", "DECIDIDO"]


class CommitteeCaseCreate(BaseModel):
    titulo: str
    descricao: str
    report_id: str | None = None
    membros: list[str] = []


class CommitteeCaseUpdate(BaseModel):
    status: str | None = None
    decisao: str | None = None
    membros: list[str] | None = None


def _case_to_dict(c: IntegrityCommitteeCase) -> dict:
    return {
        "id": str(c.id),
        "report_id": str(c.report_id) if c.report_id else None,
        "titulo": c.titulo,
        "descricao": c.descricao,
        "status": c.status,
        "decisao": c.decisao,
        "membros": c.membros or [],
        "decided_at": c.decided_at.isoformat() if c.decided_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/committee-cases")
async def list_committee_cases(
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(IntegrityCommitteeCase)
        .where(IntegrityCommitteeCase.tenant_id == current_user.tenant_id)
        .order_by(desc(IntegrityCommitteeCase.created_at))
    )).scalars().all()
    return [_case_to_dict(c) for c in rows]


@router.post("/committee-cases", status_code=201)
async def create_committee_case(
    body: CommitteeCaseCreate,
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    if not body.titulo.strip() or not body.descricao.strip():
        raise HTTPException(status_code=422, detail="Informe o título e a descrição do caso.")

    report_uuid = None
    if body.report_id:
        report = (await db.execute(
            select(IntegrityReport).where(
                IntegrityReport.id == uuid.UUID(body.report_id),
                IntegrityReport.tenant_id == current_user.tenant_id,
            )
        )).scalar_one_or_none()
        if not report:
            raise NotFoundError("Relato", body.report_id)
        report_uuid = report.id

    case = IntegrityCommitteeCase(
        tenant_id=current_user.tenant_id,
        report_id=report_uuid,
        titulo=body.titulo.strip(),
        descricao=body.descricao.strip(),
        membros=body.membros,
        created_by=current_user.id,
    )
    db.add(case)
    await db.flush()
    return _case_to_dict(case)


@router.put("/committee-cases/{case_id}")
async def update_committee_case(
    case_id: str,
    body: CommitteeCaseUpdate,
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    case = (await db.execute(
        select(IntegrityCommitteeCase).where(
            IntegrityCommitteeCase.id == uuid.UUID(case_id),
            IntegrityCommitteeCase.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if not case:
        raise NotFoundError("Caso", case_id)

    if body.status is not None:
        if body.status not in STATUS_CASO:
            raise HTTPException(status_code=422, detail=f"Status inválido. Use: {', '.join(STATUS_CASO)}")
        case.status = body.status
        if body.status == "DECIDIDO":
            case.decided_by = current_user.id
            case.decided_at = datetime.now(timezone.utc)
    if body.decisao is not None:
        case.decisao = body.decisao.strip() or None
    if body.membros is not None:
        case.membros = body.membros
    await db.flush()
    return _case_to_dict(case)
