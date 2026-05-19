"""Endpoints para gestão de documentos e petições."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Any
import uuid

from app.db.base import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.document import Document, Petition
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentResponse(BaseModel):
    id: str
    tipo: str | None
    titulo: str
    status: str
    versao: int
    gerado_por_ia: bool
    process_id: str | None
    client_id: str | None
    created_at: str


class GeneratePetitionRequest(BaseModel):
    tipo_peticao: str
    process_id: str | None = None
    client_id: str | None = None
    instrucoes: str | None = None
    processo: dict[str, Any] | None = None


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    tipo: str | None = None,
    status: str | None = None,
    process_id: str | None = None,
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Document).order_by(desc(Document.created_at)).limit(limit)
    if tipo:
        query = query.where(Document.tipo == tipo)
    if status:
        query = query.where(Document.status == status)
    if process_id:
        query = query.where(Document.process_id == uuid.UUID(process_id))

    result = await db.execute(query)
    docs = result.scalars().all()
    return [_to_response(d) for d in docs]


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Documento", doc_id)
    return _to_response(doc)


@router.get("/{doc_id}/content")
async def get_document_content(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Documento", doc_id)
    return {
        "id": str(doc.id),
        "titulo": doc.titulo,
        "conteudo_html": doc.conteudo_html,
        "conteudo_texto": doc.conteudo_texto,
        "status": doc.status,
    }


@router.post("/petitions/generate", status_code=202)
async def generate_petition(
    body: GeneratePetitionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dispara o petition_agent para geração de petição (assíncrono)."""
    from app.agents.petition.petition_agent import PetitionAgent
    from app.agents.brain.context import AgentContext

    ctx = AgentContext(
        triggered_by=current_user.id,
        task_type="generate_petition",
        task_input={
            "tipo_peticao": body.tipo_peticao,
            "instrucoes": body.instrucoes or "",
            "processo": body.processo or {},
        },
        process_id=uuid.UUID(body.process_id) if body.process_id else None,
        client_id=uuid.UUID(body.client_id) if body.client_id else None,
    )

    agent = PetitionAgent(db=db)
    result = await agent.run(ctx)

    return {
        "run_id": str(ctx.run_id),
        "status": result.status.value,
        "document_id": result.output.get("document_id"),
        "approval_required": result.approval_required,
        "warnings": result.output.get("warnings", []),
    }


@router.post("/{doc_id}/review", status_code=202)
async def review_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dispara o review_agent para revisão de um documento."""
    result = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Documento", doc_id)

    from app.agents.review.review_agent import ReviewAgent
    from app.agents.brain.context import AgentContext

    ctx = AgentContext(
        triggered_by=current_user.id,
        task_type="review_document",
        task_input={
            "conteudo": doc.conteudo_texto or "",
            "tipo_documento": doc.tipo or "PETICAO",
        },
        document_id=uuid.UUID(doc_id),
    )
    agent = ReviewAgent(db=db)
    review_result = await agent.run(ctx)

    return {
        "run_id": str(ctx.run_id),
        "document_id": doc_id,
        "status": review_result.status.value,
        "review": review_result.output,
    }


def _to_response(d: Document) -> DocumentResponse:
    return DocumentResponse(
        id=str(d.id),
        tipo=d.tipo,
        titulo=d.titulo,
        status=d.status,
        versao=d.versao,
        gerado_por_ia=d.gerado_por_ia,
        process_id=str(d.process_id) if d.process_id else None,
        client_id=str(d.client_id) if d.client_id else None,
        created_at=d.created_at.isoformat(),
    )
