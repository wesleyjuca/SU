"""CRUD de teses jurídicas (Fase 138.4) — lista controlada por escritório,
usada pra classificar processos e agrupar a taxa de êxito em
`GET /system/analytics/gestao`."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, field_validator
import uuid

from app.db.base import get_db
from app.dependencies import get_current_user, require_role
from app.models.user import User
from app.models.tese import Tese
from app.core.exceptions import NotFoundError, AFJException
from fastapi import status

router = APIRouter(prefix="/teses", tags=["teses"])


class TeseCreate(BaseModel):
    nome: str
    area_direito: str | None = None

    @field_validator("nome")
    @classmethod
    def _validar_nome(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("nome não pode ser vazio")
        return v


class TeseUpdate(BaseModel):
    nome: str | None = None
    area_direito: str | None = None
    ativo: bool | None = None

    @field_validator("nome")
    @classmethod
    def _validar_nome(cls, v):
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("nome não pode ser vazio")
        return v


class TeseResponse(BaseModel):
    id: str
    nome: str
    area_direito: str | None = None
    ativo: bool
    created_at: str


def _to_response(t: Tese) -> TeseResponse:
    return TeseResponse(
        id=str(t.id), nome=t.nome, area_direito=t.area_direito,
        ativo=t.ativo, created_at=t.created_at.isoformat(),
    )


@router.get("", response_model=list[TeseResponse])
async def list_teses(
    incluir_inativas: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Tese).where(Tese.tenant_id == current_user.tenant_id).order_by(Tese.nome)
    if not incluir_inativas:
        query = query.where(Tese.ativo == True)  # noqa: E712
    result = await db.execute(query)
    return [_to_response(t) for t in result.scalars().all()]


@router.post("", response_model=TeseResponse, status_code=201)
async def create_tese(
    body: TeseCreate,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    existe = (await db.execute(
        select(Tese.id).where(Tese.tenant_id == current_user.tenant_id, Tese.nome == body.nome)
    )).scalar_one_or_none()
    if existe:
        raise AFJException(status_code=status.HTTP_409_CONFLICT, detail="Já existe uma tese com esse nome.")
    tese = Tese(tenant_id=current_user.tenant_id, nome=body.nome, area_direito=body.area_direito)
    db.add(tese)
    await db.flush()
    return _to_response(tese)


async def _get_tese_do_tenant(db: AsyncSession, tese_id: str, tenant_id) -> Tese:
    result = await db.execute(
        select(Tese).where(Tese.id == uuid.UUID(tese_id), Tese.tenant_id == tenant_id)
    )
    tese = result.scalar_one_or_none()
    if not tese:
        raise NotFoundError("Tese", tese_id)
    return tese


@router.put("/{tese_id}", response_model=TeseResponse)
async def update_tese(
    tese_id: str,
    body: TeseUpdate,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    tese = await _get_tese_do_tenant(db, tese_id, current_user.tenant_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(tese, field, value)
    await db.flush()
    return _to_response(tese)


@router.delete("/{tese_id}", status_code=204)
async def deactivate_tese(
    tese_id: str,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    """Desativa (soft-delete) — processos já ligados a essa tese continuam
    ligados (`tese_id` só vira NULL se a linha for de fato apagada, o que
    este endpoint não faz)."""
    tese = await _get_tese_do_tenant(db, tese_id, current_user.tenant_id)
    tese.ativo = False
    await db.flush()
