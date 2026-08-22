"""Endpoints financeiros — honorários, despesas e relatórios."""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from decimal import Decimal
from datetime import date
import uuid

import re

from app.db.base import get_db
from app.dependencies import require_role
from app.models.user import User
from app.models.financial import FinancialEntry
from app.models.client import Client
from app.models.process import LegalProcess

router = APIRouter(prefix="/financial", tags=["financial"])

# Fase 184 — heurística de PII pra avisar (não bloquear) antes de mandar a
# descrição de um lançamento pra fora do sistema (Google Sheets do escritório
# é de outro Google Workspace, não necessariamente sob o mesmo controle de
# acesso do sistema). Casa CPF (3-3-3-2) e CNPJ (2-3-3-4-2) com ou sem a
# pontuação usual — "ignorando formatação" não significa remover todos os
# separadores antes (isso juntaria números não relacionados), só aceitar que
# o dado apareça pontuado ou não.
_CPF_CNPJ_LIKE_RE = re.compile(
    r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}"           # CPF: 11 dígitos
    r"|\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}"   # CNPJ: 14 dígitos
)


def _descricoes_com_possivel_pii(entries) -> list[str]:
    return [e.descricao for e in entries if e.descricao and _CPF_CNPJ_LIKE_RE.search(e.descricao)]


async def _validar_client_id(db: AsyncSession, client_id: str | None, tenant_id) -> uuid.UUID | None:
    """Garante que o client_id (se informado) pertence ao tenant — evita
    vincular um lançamento financeiro ao cliente de outro escritório."""
    if not client_id:
        return None
    cid = uuid.UUID(client_id)
    existe = (await db.execute(
        select(Client.id).where(Client.id == cid, Client.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not existe:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    return cid


async def _validar_process_id(db: AsyncSession, process_id: str | None, tenant_id) -> uuid.UUID | None:
    """Garante que o process_id (se informado) pertence ao tenant — evita
    vincular um lançamento financeiro ao processo de outro escritório."""
    if not process_id:
        return None
    pid = uuid.UUID(process_id)
    existe = (await db.execute(
        select(LegalProcess.id).where(LegalProcess.id == pid, LegalProcess.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not existe:
        raise HTTPException(status_code=404, detail="Processo não encontrado.")
    return pid


class FinancialEntryCreate(BaseModel):
    tipo: str            # RECEITA, DESPESA
    categoria: str | None = None
    client_id: str | None = None
    process_id: str | None = None
    descricao: str
    valor: float
    data_vencimento: date | None = None
    status: str = "PENDENTE"


class FinancialEntryResponse(BaseModel):
    id: str
    tipo: str
    categoria: str | None
    descricao: str
    valor: float
    status: str
    data_vencimento: str | None
    data_pagamento: str | None
    client_id: str | None
    process_id: str | None
    created_at: str


@router.get("", response_model=list[FinancialEntryResponse])
async def list_entries(
    tipo: str | None = None,
    status: str | None = None,
    client_id: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(FinancialEntry)
        .where(FinancialEntry.tenant_id == current_user.tenant_id)
        .order_by(desc(FinancialEntry.created_at))
        .offset(offset)
        .limit(limit)
    )
    if tipo:
        query = query.where(FinancialEntry.tipo == tipo)
    if status:
        query = query.where(FinancialEntry.status == status)
    if client_id:
        # Fase 210 (achado da Fase 209) — o changelog da Fase 205.3 dizia que
        # "Faturas já tinha suporte no backend", mas o parâmetro nunca foi
        # declarado aqui: FastAPI descartava `?client_id=` silenciosamente e
        # a navegação contextual do Cliente 360 devolvia TODOS os lançamentos
        # do tenant em vez de só os do cliente. Confirmado empiricamente
        # (HTTP real) que não vazava dado cross-tenant — só não filtrava.
        query = query.where(FinancialEntry.client_id == uuid.UUID(client_id))
    result = await db.execute(query)
    entries = result.scalars().all()
    return [_to_response(e) for e in entries]


@router.post("", response_model=FinancialEntryResponse, status_code=201)
async def create_entry(
    body: FinancialEntryCreate,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    entry = FinancialEntry(
        tipo=body.tipo,
        categoria=body.categoria,
        client_id=await _validar_client_id(db, body.client_id, current_user.tenant_id),
        process_id=await _validar_process_id(db, body.process_id, current_user.tenant_id),
        descricao=body.descricao,
        valor=Decimal(str(body.valor)),
        data_vencimento=body.data_vencimento,
        status=body.status,
        created_by=current_user.id,
        tenant_id=current_user.tenant_id,
    )
    db.add(entry)
    await db.flush()
    return _to_response(entry)


class FinancialEntryUpdate(BaseModel):
    descricao: str | None = None
    valor: float | None = None
    categoria: str | None = None
    data_vencimento: date | None = None
    status: str | None = None


@router.put("/{entry_id}", response_model=FinancialEntryResponse)
async def update_entry(
    entry_id: str,
    body: FinancialEntryUpdate,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    from app.core.exceptions import NotFoundError
    result = await db.execute(
        select(FinancialEntry).where(
            FinancialEntry.id == uuid.UUID(entry_id),
            FinancialEntry.tenant_id == current_user.tenant_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise NotFoundError("Lançamento", entry_id)
    updates = body.model_dump(exclude_none=True)
    if "valor" in updates:
        entry.valor = Decimal(str(updates.pop("valor")))
    for field, value in updates.items():
        setattr(entry, field, value)
    await db.flush()
    return _to_response(entry)


@router.delete("/{entry_id}", status_code=204)
async def delete_entry(
    entry_id: str,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    from app.core.exceptions import NotFoundError
    result = await db.execute(
        select(FinancialEntry).where(
            FinancialEntry.id == uuid.UUID(entry_id),
            FinancialEntry.tenant_id == current_user.tenant_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise NotFoundError("Lançamento", entry_id)
    await db.delete(entry)
    await db.flush()


@router.get("/export")
async def export_financial(
    tipo: str | None = None,
    status: str | None = None,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    """Exporta lançamentos como CSV."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    query = (
        select(FinancialEntry)
        .where(FinancialEntry.tenant_id == current_user.tenant_id)
        .order_by(desc(FinancialEntry.created_at))
    )
    if tipo:
        query = query.where(FinancialEntry.tipo == tipo)
    if status:
        query = query.where(FinancialEntry.status == status)
    result = await db.execute(query)
    entries = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Tipo", "Categoria", "Descrição", "Valor", "Status", "Vencimento", "Pagamento", "Criado em"])
    for e in entries:
        writer.writerow([
            str(e.id), e.tipo, e.categoria or "", e.descricao, float(e.valor),
            e.status,
            e.data_vencimento.isoformat() if e.data_vencimento else "",
            e.data_pagamento.isoformat() if e.data_pagamento else "",
            e.created_at.isoformat(),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=financeiro.csv"},
    )


@router.post("/export/google-sheets", status_code=201)
async def export_financial_to_google_sheets(
    tipo: str | None = None,
    status: str | None = None,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    """Fase 182 — mesma exportação de /export, mas sobe direto pro Google
    Drive do escritório já como planilha colaborável: a Drive API converte o
    CSV automaticamente no upload, sob o escopo drive.file já concedido
    (Fase 139) — sem precisar da Sheets API nem de reconexão."""
    import csv
    import io
    from app.models.tenant import TenantConfig
    from app.services.google_workspace import get_valid_token, drive_upload_sheet, GoogleNotConnected

    cfg = (await db.execute(
        select(TenantConfig).where(TenantConfig.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()
    if not (cfg and (cfg.modules_enabled or {}).get("google_workspace", False)):
        raise HTTPException(
            status_code=422,
            detail="A integração Google Workspace está desabilitada para este escritório. "
                   "O administrador pode habilitá-la em Integrações.",
        )

    query = (
        select(FinancialEntry)
        .where(FinancialEntry.tenant_id == current_user.tenant_id)
        .order_by(desc(FinancialEntry.created_at))
    )
    if tipo:
        query = query.where(FinancialEntry.tipo == tipo)
    if status:
        query = query.where(FinancialEntry.status == status)
    entries = (await db.execute(query)).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Tipo", "Categoria", "Descrição", "Valor", "Status", "Vencimento", "Pagamento", "Criado em"])
    for e in entries:
        writer.writerow([
            str(e.id), e.tipo, e.categoria or "", e.descricao, float(e.valor),
            e.status,
            e.data_vencimento.isoformat() if e.data_vencimento else "",
            e.data_pagamento.isoformat() if e.data_pagamento else "",
            e.created_at.isoformat(),
        ])

    # Fase 184 — aviso (não bloqueio) se alguma descrição parecer conter
    # CPF/CNPJ: a planilha sobe pro Drive do escritório fora do controle de
    # acesso por tenant deste sistema, então quem exporta deve saber antes/
    # depois que pode estar levando dado pessoal junto.
    descricoes_pii = _descricoes_com_possivel_pii(entries)

    try:
        token = await get_valid_token(db, current_user.tenant_id)
        result = await drive_upload_sheet(token, "financeiro", output.getvalue().encode("utf-8-sig"))
    except GoogleNotConnected as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=502, detail="Erro ao exportar pro Google Sheets.")

    # Fase 184 — mesma lacuna de rastro específico já corrigida em
    # approvals.py (Fase 174.8) e no /drive-save-doc (acima): o
    # AuditMiddleware genérico não registra resource_type/resource_id, e
    # exportar dado financeiro do escritório inteiro merece rastro próprio.
    from app.models.audit_log import AuditLog
    db.add(AuditLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="GOOGLE_EXPORT:FINANCIAL_SHEET",
        resource_type="FINANCIAL_EXPORT",
        new_value={
            "count": len(entries),
            "tipo_filter": tipo,
            "status_filter": status,
            "google_sheet_id": result.get("id"),
            "possivel_pii": bool(descricoes_pii),
        },
        contains_pii=bool(descricoes_pii),
        success=True,
    ))
    await db.flush()

    response = {"message": "Lançamentos exportados pro Google Sheets do escritório.", **result}
    if descricoes_pii:
        response["aviso_pii"] = (
            f"{len(descricoes_pii)} lançamento(s) têm descrição com um padrão parecido "
            "com CPF/CNPJ, que foi exportado junto pro Google Sheets do escritório."
        )
    return response


@router.post("/{entry_id}/mark-paid")
async def mark_paid(
    entry_id: str,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FinancialEntry).where(
            FinancialEntry.id == uuid.UUID(entry_id),
            FinancialEntry.tenant_id == current_user.tenant_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Lançamento", entry_id)
    if entry.status == "PAGO":
        return {"message": "Lançamento já estava pago", "id": entry_id}
    if entry.status == "CANCELADO":
        raise HTTPException(status_code=422, detail="Lançamento cancelado não pode ser marcado como pago.")
    entry.status = "PAGO"
    entry.data_pagamento = date.today()
    return {"message": "Marcado como pago", "id": entry_id}


@router.get("/monthly")
async def monthly_summary(
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    """Retorna receitas e despesas pagas agrupadas por mês (últimos 6 meses)."""
    from sqlalchemy import func, extract
    from datetime import date, timedelta

    six_months_ago = date.today().replace(day=1) - timedelta(days=150)
    result = await db.execute(
        select(
            extract("year", FinancialEntry.created_at).label("ano"),
            extract("month", FinancialEntry.created_at).label("mes"),
            FinancialEntry.tipo,
            func.sum(FinancialEntry.valor).label("total"),
        )
        .where(
            FinancialEntry.tenant_id == current_user.tenant_id,
            FinancialEntry.status == "PAGO",
            FinancialEntry.created_at >= six_months_ago,
        )
        .group_by("ano", "mes", FinancialEntry.tipo)
        .order_by("ano", "mes")
    )
    rows = result.all()

    months: dict[str, dict] = {}
    for row in rows:
        key = f"{int(row.ano)}-{int(row.mes):02d}"
        if key not in months:
            months[key] = {"mes": key, "receitas": 0.0, "despesas": 0.0}
        if row.tipo == "RECEITA":
            months[key]["receitas"] = float(row.total)
        else:
            months[key]["despesas"] = float(row.total)

    return {"data": list(months.values())}


@router.get("/summary")
async def financial_summary(
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    """Resumo financeiro do escritório (receitas/despesas pagas e pendentes).

    Retorna exatamente as chaves que a tela de Financeiro consome — antes o
    endpoint devolvia chaves do FinancialAgent (receita_recebida etc.) que não
    batiam com a página, deixando os 4 KPIs sempre em R$ 0,00.
    """
    from sqlalchemy import func

    rows = (await db.execute(
        select(
            FinancialEntry.tipo,
            FinancialEntry.status,
            func.coalesce(func.sum(FinancialEntry.valor), 0),
        )
        .where(FinancialEntry.tenant_id == current_user.tenant_id)  # isolamento multi-tenant
        .group_by(FinancialEntry.tipo, FinancialEntry.status)
    )).all()

    agg: dict[tuple[str, str], float] = {(t, s): float(v or 0) for t, s, v in rows}
    receitas_pagas = agg.get(("RECEITA", "PAGO"), 0.0)
    receitas_pendentes = agg.get(("RECEITA", "PENDENTE"), 0.0)
    despesas_pagas = agg.get(("DESPESA", "PAGO"), 0.0)
    despesas_pendentes = agg.get(("DESPESA", "PENDENTE"), 0.0)

    return {
        "receitas_pagas": receitas_pagas,
        "receitas_pendentes": receitas_pendentes,
        "despesas_pagas": despesas_pagas,
        "despesas_pendentes": despesas_pendentes,
        "saldo_atual": receitas_pagas - despesas_pagas,
        "a_receber": receitas_pendentes,
    }


@router.get("/overdue")
async def financial_overdue(
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    """Inadimplência: receitas PENDENTES já vencidas (data_vencimento < hoje)."""
    from datetime import date as _date

    vencidos = (await db.execute(
        select(FinancialEntry).where(
            FinancialEntry.tenant_id == current_user.tenant_id,  # isolamento multi-tenant
            FinancialEntry.tipo == "RECEITA",
            FinancialEntry.status == "PENDENTE",
            FinancialEntry.data_vencimento.is_not(None),
            FinancialEntry.data_vencimento < _date.today(),
        ).order_by(FinancialEntry.data_vencimento)
    )).scalars().all()

    hoje = _date.today()
    return {
        "total": len(vencidos),
        "valor_total": float(sum(e.valor for e in vencidos)),
        "registros": [
            {
                "id": str(e.id),
                "descricao": e.descricao,
                "categoria": e.categoria,
                "valor": float(e.valor),
                "vencimento": e.data_vencimento.isoformat() if e.data_vencimento else None,
                "dias_atraso": (hoje - e.data_vencimento).days if e.data_vencimento else None,
                "client_id": str(e.client_id) if e.client_id else None,
            }
            for e in vencidos
        ],
    }


def _to_response(e: FinancialEntry) -> FinancialEntryResponse:
    return FinancialEntryResponse(
        id=str(e.id),
        tipo=e.tipo,
        categoria=e.categoria,
        descricao=e.descricao,
        valor=float(e.valor),
        status=e.status,
        data_vencimento=e.data_vencimento.isoformat() if e.data_vencimento else None,
        data_pagamento=e.data_pagamento.isoformat() if e.data_pagamento else None,
        client_id=str(e.client_id) if e.client_id else None,
        process_id=str(e.process_id) if e.process_id else None,
        created_at=e.created_at.isoformat(),
    )
