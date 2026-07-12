"""CRM — funil de vendas (oportunidades)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from datetime import date
from decimal import Decimal
import uuid

from app.db.base import get_db
from app.dependencies import require_role
from app.models.user import User
from app.models.crm import Opportunity
from app.models.client import Client

router = APIRouter(prefix="/crm", tags=["crm"])

ESTAGIOS = ["LEAD", "QUALIFICACAO", "PROPOSTA", "NEGOCIACAO", "GANHO", "PERDIDO"]
_ABERTOS = ("LEAD", "QUALIFICACAO", "PROPOSTA", "NEGOCIACAO")
_STAFF = require_role("ADMIN", "SOCIO", "ADVOGADO", "GESTOR")


class OppCreate(BaseModel):
    titulo: str
    valor_estimado: Decimal = Field(default=0, ge=0)
    estagio: str = "LEAD"
    probabilidade: int = Field(default=50, ge=0, le=100)
    client_id: str | None = None
    descricao: str | None = None
    origem: str | None = None
    responsavel_id: str | None = None
    expected_close: str | None = None


class OppPatch(BaseModel):
    titulo: str | None = None
    valor_estimado: Decimal | None = Field(default=None, ge=0)
    estagio: str | None = None
    probabilidade: int | None = Field(default=None, ge=0, le=100)
    client_id: str | None = None
    descricao: str | None = None
    origem: str | None = None
    expected_close: str | None = None
    motivo_perda: str | None = None


def _to_dict(o: Opportunity, cliente: str | None = None) -> dict:
    return {
        "id": str(o.id),
        "titulo": o.titulo,
        "descricao": o.descricao,
        "valor_estimado": float(o.valor_estimado or 0),
        "estagio": o.estagio,
        "probabilidade": o.probabilidade,
        "origem": o.origem,
        "client_id": str(o.client_id) if o.client_id else None,
        "cliente": cliente,
        "responsavel_id": str(o.responsavel_id) if o.responsavel_id else None,
        "expected_close": o.expected_close.isoformat() if o.expected_close else None,
        "motivo_perda": o.motivo_perda,
    }


async def _nomes_clientes(db: AsyncSession, opps: list[Opportunity]) -> dict:
    cids = [o.client_id for o in opps if o.client_id]
    if not cids:
        return {}
    return {c.id: c.nome_completo for c in (await db.execute(select(Client).where(Client.id.in_(cids)))).scalars().all()}


async def _get_opp(db: AsyncSession, opp_id: str, tenant_id) -> Opportunity:
    o = (await db.execute(
        select(Opportunity).where(Opportunity.id == uuid.UUID(opp_id), Opportunity.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not o:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada.")
    return o


@router.get("/funil")
async def funil(current_user: User = Depends(_STAFF), db: AsyncSession = Depends(get_db)):
    """Kanban: oportunidades por estágio + forecast ponderado das abertas."""
    opps = (await db.execute(
        select(Opportunity).where(Opportunity.tenant_id == current_user.tenant_id)
        .order_by(Opportunity.created_at.desc())
    )).scalars().all()
    nomes = await _nomes_clientes(db, opps)

    colunas = {e: [] for e in ESTAGIOS}
    totais = {e: {"count": 0, "valor": 0.0} for e in ESTAGIOS}
    forecast = 0.0
    for o in opps:
        est = o.estagio if o.estagio in colunas else "LEAD"
        colunas[est].append(_to_dict(o, nomes.get(o.client_id)))
        totais[est]["count"] += 1
        totais[est]["valor"] += float(o.valor_estimado or 0)
        if est in _ABERTOS:
            forecast += float(o.valor_estimado or 0) * (o.probabilidade or 0) / 100.0

    pipeline_aberto = sum(totais[e]["valor"] for e in _ABERTOS)
    return {
        "estagios": ESTAGIOS,
        "colunas": colunas,
        "totais": totais,
        "forecast": round(forecast, 2),
        "pipeline_aberto": round(pipeline_aberto, 2),
        "abertas": sum(totais[e]["count"] for e in _ABERTOS),
    }


@router.get("/opportunities")
async def list_opps(
    estagio: str | None = Query(default=None),
    current_user: User = Depends(_STAFF),
    db: AsyncSession = Depends(get_db),
):
    q = select(Opportunity).where(Opportunity.tenant_id == current_user.tenant_id)
    if estagio:
        q = q.where(Opportunity.estagio == estagio)
    opps = (await db.execute(q.order_by(Opportunity.created_at.desc()))).scalars().all()
    nomes = await _nomes_clientes(db, opps)
    return [_to_dict(o, nomes.get(o.client_id)) for o in opps]


@router.post("/opportunities", status_code=201)
async def create_opp(body: OppCreate, current_user: User = Depends(_STAFF), db: AsyncSession = Depends(get_db)):
    if body.estagio not in ESTAGIOS:
        raise HTTPException(status_code=422, detail=f"Estágio inválido. Use: {', '.join(ESTAGIOS)}")
    o = Opportunity(
        tenant_id=current_user.tenant_id,
        titulo=body.titulo,
        descricao=body.descricao,
        valor_estimado=body.valor_estimado,
        estagio=body.estagio,
        probabilidade=body.probabilidade,
        origem=body.origem,
        client_id=uuid.UUID(body.client_id) if body.client_id else None,
        responsavel_id=uuid.UUID(body.responsavel_id) if body.responsavel_id else current_user.id,
        expected_close=date.fromisoformat(body.expected_close) if body.expected_close else None,
    )
    db.add(o)
    await db.commit()
    return _to_dict(o)


@router.patch("/opportunities/{opp_id}")
async def patch_opp(opp_id: str, body: OppPatch, current_user: User = Depends(_STAFF), db: AsyncSession = Depends(get_db)):
    o = await _get_opp(db, opp_id, current_user.tenant_id)
    data = body.model_dump(exclude_none=True)

    if "estagio" in data:
        if data["estagio"] not in ESTAGIOS:
            raise HTTPException(status_code=422, detail="Estágio inválido.")
        if data["estagio"] == "PERDIDO" and not (data.get("motivo_perda") or o.motivo_perda):
            raise HTTPException(status_code=422, detail="Informe o motivo da perda.")
        # Conversão leve: GANHO ativa o cliente vinculado.
        if data["estagio"] == "GANHO" and o.client_id:
            cli = (await db.execute(
                select(Client).where(Client.id == o.client_id, Client.tenant_id == current_user.tenant_id)
            )).scalar_one_or_none()
            if cli:
                cli.status = "ATIVO"

    for field, value in data.items():
        if field == "client_id":
            o.client_id = uuid.UUID(value) if value else None
        elif field == "expected_close":
            o.expected_close = date.fromisoformat(value) if value else None
        else:
            setattr(o, field, value)
    await db.commit()
    return _to_dict(o)


@router.delete("/opportunities/{opp_id}", status_code=204)
async def delete_opp(opp_id: str, current_user: User = Depends(_STAFF), db: AsyncSession = Depends(get_db)):
    o = await _get_opp(db, opp_id, current_user.tenant_id)
    await db.delete(o)
    await db.commit()
