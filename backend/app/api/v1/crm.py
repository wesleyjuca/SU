"""CRM — funil de vendas (oportunidades)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, or_
from pydantic import BaseModel, Field
from datetime import date
from decimal import Decimal
import uuid

from app.db.base import get_db
from app.dependencies import require_role
from app.models.user import User
from app.models.crm import Opportunity
from app.models.client import Client
from app.models.financial import FinancialEntry

router = APIRouter(prefix="/crm", tags=["crm"])

ESTAGIOS = ["LEAD", "QUALIFICACAO", "PROPOSTA", "NEGOCIACAO", "GANHO", "PERDIDO"]
_ABERTOS = ("LEAD", "QUALIFICACAO", "PROPOSTA", "NEGOCIACAO")
_STAFF = require_role("ADMIN", "SOCIO", "ADVOGADO", "GESTOR")
# Fase 161 — cards renderizados por coluna do Kanban, por estágio. Estágios
# terminais (GANHO/PERDIDO) nunca são removidos e acumulam pra sempre —
# sem esse teto, o funil carregaria centenas/milhares de cards conforme o
# pipeline envelhece. totais/forecast continuam refletindo TODAS as
# oportunidades (agregação SQL, não afetada por este teto).
FUNIL_CARD_LIMIT = 100


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


async def _nomes_clientes(db: AsyncSession, opps: list[Opportunity], tenant_id) -> dict:
    cids = [o.client_id for o in opps if o.client_id]
    if not cids:
        return {}
    return {c.id: c.nome_completo for c in (await db.execute(
        select(Client).where(Client.id.in_(cids), Client.tenant_id == tenant_id)
    )).scalars().all()}


async def _validar_client_id(db: AsyncSession, client_id: str | None, tenant_id) -> uuid.UUID | None:
    """Garante que o client_id (se informado) pertence ao tenant do usuário —
    evita vazamento cross-tenant de nome de cliente no funil de vendas."""
    if not client_id:
        return None
    cid = uuid.UUID(client_id)
    existe = (await db.execute(
        select(Client.id).where(Client.id == cid, Client.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not existe:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    return cid


async def _get_opp(db: AsyncSession, opp_id: str, tenant_id) -> Opportunity:
    o = (await db.execute(
        select(Opportunity).where(Opportunity.id == uuid.UUID(opp_id), Opportunity.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not o:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada.")
    return o


@router.get("/funil")
async def funil(current_user: User = Depends(_STAFF), db: AsyncSession = Depends(get_db)):
    """Kanban: oportunidades por estágio + forecast ponderado das abertas.

    Fase 161 — `totais`/`forecast`/`pipeline_aberto` vêm de uma agregação SQL
    sobre TODAS as oportunidades do tenant (nunca truncados). Os cards de
    cada coluna (`colunas`) são limitados a `FUNIL_CARD_LIMIT` mais recentes
    por estágio — `truncado[estagio]` sinaliza quando a coluna tem mais
    oportunidades do que as exibidas (nunca um teto silencioso)."""
    agg_rows = (await db.execute(
        select(
            Opportunity.estagio,
            func.count().label("count"),
            func.coalesce(func.sum(Opportunity.valor_estimado), 0).label("valor"),
            func.coalesce(func.sum(
                case(
                    (Opportunity.estagio.in_(_ABERTOS),
                     Opportunity.valor_estimado * Opportunity.probabilidade / 100.0),
                    else_=0,
                )
            ), 0).label("forecast_parcial"),
        )
        .where(Opportunity.tenant_id == current_user.tenant_id)
        .group_by(Opportunity.estagio)
    )).all()

    totais = {e: {"count": 0, "valor": 0.0} for e in ESTAGIOS}
    forecast = 0.0
    for row in agg_rows:
        est = row.estagio if row.estagio in totais else "LEAD"
        totais[est]["count"] += row.count
        totais[est]["valor"] += float(row.valor or 0)
        forecast += float(row.forecast_parcial or 0)

    colunas: dict = {}
    truncado: dict = {}
    for est in ESTAGIOS:
        condicao_estagio = (
            or_(Opportunity.estagio == "LEAD", Opportunity.estagio.not_in(ESTAGIOS))
            if est == "LEAD" else Opportunity.estagio == est
        )
        opps_est = (await db.execute(
            select(Opportunity)
            .where(Opportunity.tenant_id == current_user.tenant_id, condicao_estagio)
            .order_by(Opportunity.created_at.desc())
            .limit(FUNIL_CARD_LIMIT)
        )).scalars().all()
        nomes = await _nomes_clientes(db, opps_est, current_user.tenant_id)
        colunas[est] = [_to_dict(o, nomes.get(o.client_id)) for o in opps_est]
        truncado[est] = totais[est]["count"] > len(opps_est)

    pipeline_aberto = sum(totais[e]["valor"] for e in _ABERTOS)
    return {
        "estagios": ESTAGIOS,
        "colunas": colunas,
        "totais": totais,
        "truncado": truncado,
        "forecast": round(forecast, 2),
        "pipeline_aberto": round(pipeline_aberto, 2),
        "abertas": sum(totais[e]["count"] for e in _ABERTOS),
    }


@router.get("/previsao-caixa")
async def previsao_caixa(current_user: User = Depends(_STAFF), db: AsyncSession = Depends(get_db)):
    """Fase 208.2 — previsão de caixa dos próximos 6 meses, combinando o
    pipeline do CRM (`Opportunity` aberta, ponderada por `probabilidade`,
    mesmo cálculo do `/funil`) com receita já PENDENTE (`FinancialEntry`).
    Os dois ficam separados na resposta (nunca somados num único número
    "previsto") — pipeline é probabilístico, receita_prevista já está
    faturada/comprometida; fundir os dois esconderia essa diferença."""
    hoje = date.today()
    meses: list[tuple[int, int]] = []
    y, m = hoje.year, hoje.month
    for _ in range(6):
        meses.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    inicio = date(meses[0][0], meses[0][1], 1)
    fim_y, fim_m = meses[-1]
    fim_m += 1
    if fim_m > 12:
        fim_m = 1
        fim_y += 1
    fim = date(fim_y, fim_m, 1)  # limite exclusivo

    opps = (await db.execute(
        select(Opportunity.expected_close, Opportunity.valor_estimado, Opportunity.probabilidade)
        .where(
            Opportunity.tenant_id == current_user.tenant_id,
            Opportunity.estagio.in_(_ABERTOS),
            Opportunity.expected_close.is_not(None),
            Opportunity.expected_close >= inicio,
            Opportunity.expected_close < fim,
        )
    )).all()
    receitas = (await db.execute(
        select(FinancialEntry.data_vencimento, FinancialEntry.valor)
        .where(
            FinancialEntry.tenant_id == current_user.tenant_id,
            FinancialEntry.tipo == "RECEITA",
            FinancialEntry.status == "PENDENTE",
            FinancialEntry.data_vencimento.is_not(None),
            FinancialEntry.data_vencimento >= inicio,
            FinancialEntry.data_vencimento < fim,
        )
    )).all()

    pipeline_por_mes = {ym: 0.0 for ym in meses}
    for exp, valor, prob in opps:
        pipeline_por_mes[(exp.year, exp.month)] += float(valor or 0) * (prob or 0) / 100.0

    receita_por_mes = {ym: 0.0 for ym in meses}
    for venc, valor in receitas:
        receita_por_mes[(venc.year, venc.month)] += float(valor or 0)

    meses_resp = []
    for (ano, mes) in meses:
        pipeline = round(pipeline_por_mes[(ano, mes)], 2)
        receita = round(receita_por_mes[(ano, mes)], 2)
        meses_resp.append({
            "mes": f"{ano:04d}-{mes:02d}",
            "pipeline_ponderado": pipeline,
            "receita_prevista": receita,
            "total": round(pipeline + receita, 2),
        })
    return {"meses": meses_resp}


@router.get("/opportunities")
async def list_opps(
    estagio: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    current_user: User = Depends(_STAFF),
    db: AsyncSession = Depends(get_db),
):
    q = select(Opportunity).where(Opportunity.tenant_id == current_user.tenant_id)
    if estagio:
        q = q.where(Opportunity.estagio == estagio)
    q = q.order_by(Opportunity.created_at.desc()).offset(offset).limit(limit)
    opps = (await db.execute(q)).scalars().all()
    nomes = await _nomes_clientes(db, opps, current_user.tenant_id)
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
        client_id=await _validar_client_id(db, body.client_id, current_user.tenant_id),
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
            o.client_id = await _validar_client_id(db, value, current_user.tenant_id)
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
