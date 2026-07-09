"""CRUD de modelos de petição reutilizáveis (tenant-scoped)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
import uuid

from app.db.base import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.document import PetitionTemplate
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/petition-templates", tags=["petition-templates"])


class TemplateResponse(BaseModel):
    id: str
    nome: str
    tipo_peticao: str | None
    descricao: str | None
    conteudo: str
    ativo: bool
    created_at: str


class TemplateCreate(BaseModel):
    nome: str
    tipo_peticao: str | None = None
    descricao: str | None = None
    conteudo: str
    ativo: bool = True


class TemplateUpdate(BaseModel):
    nome: str | None = None
    tipo_peticao: str | None = None
    descricao: str | None = None
    conteudo: str | None = None
    ativo: bool | None = None


def _to_response(t: PetitionTemplate) -> TemplateResponse:
    return TemplateResponse(
        id=str(t.id),
        nome=t.nome,
        tipo_peticao=t.tipo_peticao,
        descricao=t.descricao,
        conteudo=t.conteudo,
        ativo=t.ativo,
        created_at=t.created_at.isoformat(),
    )


@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    tipo_peticao: str | None = None,
    ativo: bool | None = None,
    limit: int = Query(default=100, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(PetitionTemplate)
        .where(PetitionTemplate.tenant_id == current_user.tenant_id)
        .order_by(desc(PetitionTemplate.created_at))
        .limit(limit)
    )
    if tipo_peticao:
        query = query.where(PetitionTemplate.tipo_peticao == tipo_peticao)
    if ativo is not None:
        query = query.where(PetitionTemplate.ativo == ativo)
    result = await db.execute(query)
    return [_to_response(t) for t in result.scalars().all()]


@router.post("", status_code=201, response_model=TemplateResponse)
async def create_template(
    body: TemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tpl = PetitionTemplate(
        nome=body.nome,
        tipo_peticao=body.tipo_peticao,
        descricao=body.descricao,
        conteudo=body.conteudo,
        ativo=body.ativo,
        created_by=current_user.id,
        tenant_id=current_user.tenant_id,
    )
    db.add(tpl)
    await db.flush()
    return _to_response(tpl)


async def _get_owned(db: AsyncSession, template_id: str, current_user: User) -> PetitionTemplate:
    result = await db.execute(
        select(PetitionTemplate).where(
            PetitionTemplate.id == uuid.UUID(template_id),
            PetitionTemplate.tenant_id == current_user.tenant_id,
        )
    )
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise NotFoundError("PetitionTemplate", template_id)
    return tpl


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: str,
    body: TemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tpl = await _get_owned(db, template_id, current_user)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(tpl, field, value)
    await db.flush()
    return _to_response(tpl)


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tpl = await _get_owned(db, template_id, current_user)
    await db.delete(tpl)
    await db.flush()
