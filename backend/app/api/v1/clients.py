"""Endpoints CRUD de clientes / CRM."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_
from pydantic import BaseModel, EmailStr
from typing import Any
import uuid
from datetime import datetime, timezone

from app.db.base import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.client import Client, ClientInteraction
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/clients", tags=["clients"])


class ClientCreate(BaseModel):
    tipo: str  # PF, PJ
    nome_completo: str
    razao_social: str | None = None
    email: str | None = None
    telefone: str | None = None
    whatsapp: str | None = None
    cpf: str | None = None
    cnpj: str | None = None
    origem: str | None = None
    status: str = "PROSPECTO"
    observacoes: str | None = None
    lgpd_consent: bool = False


class ClientResponse(BaseModel):
    id: str
    tipo: str
    nome_completo: str
    razao_social: str | None
    email: str | None
    telefone: str | None
    whatsapp: str | None
    status: str
    origem: str | None
    lgpd_consent: bool
    created_at: str


class InteractionCreate(BaseModel):
    tipo: str  # EMAIL, LIGACAO, REUNIAO, WHATSAPP, SISTEMA
    descricao: str
    metadata_json: dict[str, Any] | None = None


@router.get("", response_model=list[ClientResponse])
async def list_clients(
    status: str | None = None,
    search: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Client).order_by(desc(Client.created_at)).offset(offset).limit(limit)
    if status:
        query = query.where(Client.status == status)
    if search:
        query = query.where(
            or_(
                Client.nome_completo.ilike(f"%{search}%"),
                Client.email.ilike(f"%{search}%"),
                Client.razao_social.ilike(f"%{search}%"),
            )
        )
    result = await db.execute(query)
    clients = result.scalars().all()
    return [_to_response(c) for c in clients]


@router.post("", response_model=ClientResponse, status_code=201)
async def create_client(
    body: ClientCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_none=True)
    if body.lgpd_consent:
        data["lgpd_consent_at"] = datetime.now(timezone.utc)
    data["responsavel_id"] = current_user.id

    client = Client(**data)
    db.add(client)
    await db.flush()
    return _to_response(client)


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Client).where(Client.id == uuid.UUID(client_id)))
    client = result.scalar_one_or_none()
    if not client:
        raise NotFoundError("Cliente", client_id)
    return _to_response(client)


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: str,
    body: ClientCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Client).where(Client.id == uuid.UUID(client_id)))
    client = result.scalar_one_or_none()
    if not client:
        raise NotFoundError("Cliente", client_id)

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(client, field, value)
    if body.lgpd_consent and not client.lgpd_consent:
        client.lgpd_consent_at = datetime.now(timezone.utc)

    return _to_response(client)


@router.post("/{client_id}/interactions", status_code=201)
async def add_interaction(
    client_id: str,
    body: InteractionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Client).where(Client.id == uuid.UUID(client_id)))
    if not result.scalar_one_or_none():
        raise NotFoundError("Cliente", client_id)

    interaction = ClientInteraction(
        client_id=uuid.UUID(client_id),
        user_id=current_user.id,
        tipo=body.tipo,
        descricao=body.descricao,
        metadata_json=body.metadata_json,
    )
    db.add(interaction)
    return {"message": "Interação registrada", "client_id": client_id}


@router.get("/{client_id}/interactions")
async def get_interactions(
    client_id: str,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ClientInteraction)
        .where(ClientInteraction.client_id == uuid.UUID(client_id))
        .order_by(desc(ClientInteraction.created_at))
        .limit(limit)
    )
    interactions = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "tipo": i.tipo,
            "descricao": i.descricao,
            "created_at": i.created_at.isoformat(),
        }
        for i in interactions
    ]


def _to_response(c: Client) -> ClientResponse:
    return ClientResponse(
        id=str(c.id),
        tipo=c.tipo,
        nome_completo=c.nome_completo,
        razao_social=c.razao_social,
        email=c.email,
        telefone=c.telefone,
        whatsapp=c.whatsapp,
        status=c.status,
        origem=c.origem,
        lgpd_consent=c.lgpd_consent,
        created_at=c.created_at.isoformat(),
    )
