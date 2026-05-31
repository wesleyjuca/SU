"""Portal do Cliente — endpoints read-only acessíveis com role CLIENT."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import uuid

from app.db.base import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.client import Client
from app.models.process import LegalProcess, ProcessMovement, ProcessDeadline
from app.models.document import Document
from app.models.financial import FinancialEntry
from app.core.exceptions import ForbiddenError

router = APIRouter(prefix="/portal", tags=["portal"])


async def get_portal_client(
    current_user: User = Depends(get_current_user),
) -> tuple[User, uuid.UUID]:
    if current_user.role != "CLIENT":
        raise ForbiddenError("Acesso exclusivo para clientes do escritório")
    if not current_user.linked_client_id:
        raise ForbiddenError("Usuário não vinculado a nenhum cliente")
    return current_user, current_user.linked_client_id


@router.get("/me")
async def portal_me(
    ctx: tuple[User, uuid.UUID] = Depends(get_portal_client),
    db: AsyncSession = Depends(get_db),
):
    user, client_id = ctx
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    return {
        "user_id": str(user.id),
        "full_name": user.full_name,
        "email": user.email,
        "client": {
            "id": str(client.id),
            "tipo": client.tipo,
            "nome_completo": client.nome_completo,
            "razao_social": client.razao_social,
            "status": client.status,
        } if client else None,
    }


@router.get("/summary")
async def portal_summary(
    ctx: tuple[User, uuid.UUID] = Depends(get_portal_client),
    db: AsyncSession = Depends(get_db),
):
    user, client_id = ctx

    proc_result = await db.execute(
        select(LegalProcess).where(
            LegalProcess.client_id == client_id,
            LegalProcess.situacao == "ATIVO",
            LegalProcess.tenant_id == user.tenant_id,
        )
    )
    active_processes = len(proc_result.scalars().all())

    doc_result = await db.execute(
        select(Document).where(
            Document.client_id == client_id,
            Document.status.in_(["APROVADO", "PROTOCOLADO"]),
            Document.tenant_id == user.tenant_id,
        )
    )
    available_docs = len(doc_result.scalars().all())

    fin_result = await db.execute(
        select(FinancialEntry).where(
            FinancialEntry.client_id == client_id,
            FinancialEntry.tipo == "RECEITA",
            FinancialEntry.status == "PENDENTE",
            FinancialEntry.tenant_id == user.tenant_id,
        )
    )
    pending_entries = fin_result.scalars().all()
    outstanding_total = float(sum(e.valor for e in pending_entries))

    return {
        "active_processes": active_processes,
        "available_docs": available_docs,
        "outstanding_total": outstanding_total,
    }


@router.get("/processes")
async def portal_processes(
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    ctx: tuple[User, uuid.UUID] = Depends(get_portal_client),
    db: AsyncSession = Depends(get_db),
):
    user, client_id = ctx
    result = await db.execute(
        select(LegalProcess)
        .where(
            LegalProcess.client_id == client_id,
            LegalProcess.tenant_id == user.tenant_id,
        )
        .order_by(desc(LegalProcess.updated_at))
        .limit(limit)
        .offset(offset)
    )
    processes = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "numero_cnj": p.numero_cnj,
            "tribunal": p.tribunal,
            "vara": p.vara,
            "comarca": p.comarca,
            "area_direito": p.area_direito,
            "tipo_acao": p.tipo_acao,
            "fase": p.fase,
            "situacao": p.situacao,
            "polo": p.polo,
            "valor_causa": float(p.valor_causa) if p.valor_causa else None,
            "proximo_prazo_at": p.proximo_prazo_at.isoformat() if p.proximo_prazo_at else None,
            "ultimo_andamento_at": p.ultimo_andamento_at.isoformat() if p.ultimo_andamento_at else None,
            "distribuicao_data": p.distribuicao_data.isoformat() if p.distribuicao_data else None,
        }
        for p in processes
    ]


@router.get("/processes/{process_id}")
async def portal_process_detail(
    process_id: str,
    ctx: tuple[User, uuid.UUID] = Depends(get_portal_client),
    db: AsyncSession = Depends(get_db),
):
    user, client_id = ctx
    result = await db.execute(
        select(LegalProcess).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.client_id == client_id,
            LegalProcess.tenant_id == user.tenant_id,
        )
    )
    process = result.scalar_one_or_none()
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    movements_result = await db.execute(
        select(ProcessMovement)
        .where(ProcessMovement.process_id == process.id)
        .order_by(desc(ProcessMovement.data_movimento))
        .limit(30)
    )
    movements = movements_result.scalars().all()

    deadlines_result = await db.execute(
        select(ProcessDeadline)
        .where(
            ProcessDeadline.process_id == process.id,
            ProcessDeadline.status == "PENDENTE",
        )
        .order_by(ProcessDeadline.data_prazo)
    )
    deadlines = deadlines_result.scalars().all()

    return {
        "id": str(process.id),
        "numero_cnj": process.numero_cnj,
        "tribunal": process.tribunal,
        "vara": process.vara,
        "comarca": process.comarca,
        "uf": process.uf,
        "area_direito": process.area_direito,
        "tipo_acao": process.tipo_acao,
        "fase": process.fase,
        "situacao": process.situacao,
        "polo": process.polo,
        "valor_causa": float(process.valor_causa) if process.valor_causa else None,
        "parte_contraria": process.parte_contraria,
        "distribuicao_data": process.distribuicao_data.isoformat() if process.distribuicao_data else None,
        "movements": [
            {
                "id": str(m.id),
                "data_movimento": m.data_movimento.isoformat() if m.data_movimento else None,
                "descricao": m.descricao,
                "tipo": m.tipo,
                "ai_summary": m.ai_summary,
            }
            for m in movements
        ],
        "deadlines": [
            {
                "id": str(d.id),
                "descricao": d.descricao,
                "data_prazo": d.data_prazo.isoformat() if d.data_prazo else None,
                "data_fatal": d.data_fatal.isoformat() if d.data_fatal else None,
                "tipo": d.tipo,
            }
            for d in deadlines
        ],
    }


@router.get("/documents")
async def portal_documents(
    tipo: str | None = None,
    ctx: tuple[User, uuid.UUID] = Depends(get_portal_client),
    db: AsyncSession = Depends(get_db),
):
    user, client_id = ctx
    query = select(Document).where(
        Document.client_id == client_id,
        Document.status.in_(["APROVADO", "PROTOCOLADO"]),
        Document.tenant_id == user.tenant_id,
    )
    if tipo:
        query = query.where(Document.tipo == tipo)
    query = query.order_by(desc(Document.created_at))
    result = await db.execute(query)
    docs = result.scalars().all()
    return [
        {
            "id": str(d.id),
            "titulo": d.titulo,
            "tipo": d.tipo,
            "status": d.status,
            "versao": d.versao,
            "gerado_por_ia": d.gerado_por_ia,
            "created_at": d.created_at.isoformat(),
        }
        for d in docs
    ]


@router.get("/documents/{doc_id}/content")
async def portal_document_content(
    doc_id: str,
    ctx: tuple[User, uuid.UUID] = Depends(get_portal_client),
    db: AsyncSession = Depends(get_db),
):
    user, client_id = ctx
    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(doc_id),
            Document.client_id == client_id,
            Document.status.in_(["APROVADO", "PROTOCOLADO"]),
            Document.tenant_id == user.tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return {
        "id": str(doc.id),
        "titulo": doc.titulo,
        "tipo": doc.tipo,
        "conteudo_html": doc.conteudo_html,
        "conteudo_texto": doc.conteudo_texto,
        "arquivo_url": doc.arquivo_url,
    }


@router.get("/financial")
async def portal_financial(
    ctx: tuple[User, uuid.UUID] = Depends(get_portal_client),
    db: AsyncSession = Depends(get_db),
):
    user, client_id = ctx
    result = await db.execute(
        select(FinancialEntry)
        .where(
            FinancialEntry.client_id == client_id,
            FinancialEntry.tenant_id == user.tenant_id,
        )
        .order_by(desc(FinancialEntry.created_at))
        .limit(100)
    )
    entries = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "tipo": e.tipo,
            "categoria": e.categoria,
            "descricao": e.descricao,
            "valor": float(e.valor),
            "status": e.status,
            "data_vencimento": e.data_vencimento.isoformat() if e.data_vencimento else None,
            "data_pagamento": e.data_pagamento.isoformat() if e.data_pagamento else None,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]
