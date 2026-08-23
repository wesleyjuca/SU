"""Fase 216 (proposta de evolução da Fase 209) — playbooks de agentes por
área do direito: orientação/checklist editável, injetada no prompt do
`strategy_agent` sempre que a área bater. Arquivo próprio (não `crm.py`
nem `agent_prompts.py` — não é dado de CRM, nem config de agente
platform-wide como `AgentPromptConfig`)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.db.base import get_db
from app.dependencies import require_role
from app.models.user import User
from app.models.agent_playbook import AgentAreaPlaybook

router = APIRouter(prefix="/playbooks", tags=["playbooks"])

_GESTAO = require_role("ADMIN", "SOCIO", "GESTOR")
_STAFF = require_role("ADMIN", "SOCIO", "ADVOGADO", "GESTOR")


class PlaybookCreate(BaseModel):
    area_direito: str
    texto: str


@router.get("")
async def list_playbooks(current_user: User = Depends(_STAFF), db: AsyncSession = Depends(get_db)):
    """Lista todos os playbooks já cadastrados pro tenant — sem filtro por
    área, a UI quer ver a cobertura de uma vez."""
    rows = (await db.execute(
        select(AgentAreaPlaybook).where(AgentAreaPlaybook.tenant_id == current_user.tenant_id)
        .order_by(AgentAreaPlaybook.area_direito)
    )).scalars().all()
    return [
        {"id": str(p.id), "area_direito": p.area_direito, "texto": p.texto, "updated_at": p.updated_at.isoformat()}
        for p in rows
    ]


@router.post("", status_code=201)
async def create_or_update_playbook(
    body: PlaybookCreate, current_user: User = Depends(_GESTAO), db: AsyncSession = Depends(get_db),
):
    """Upsert: revisar a orientação de uma área já cadastrada é o caso
    comum, mesmo espírito de `create_or_update_meta` (crm.py, Fase 213)."""
    existente = (await db.execute(
        select(AgentAreaPlaybook).where(
            AgentAreaPlaybook.tenant_id == current_user.tenant_id,
            AgentAreaPlaybook.area_direito == body.area_direito,
        )
    )).scalar_one_or_none()
    if existente:
        existente.texto = body.texto
        existente.atualizado_por = current_user.id
        p = existente
    else:
        p = AgentAreaPlaybook(
            tenant_id=current_user.tenant_id, area_direito=body.area_direito,
            texto=body.texto, atualizado_por=current_user.id,
        )
        db.add(p)
    await db.commit()
    return {"id": str(p.id), "area_direito": p.area_direito, "texto": p.texto}


@router.delete("/{playbook_id}", status_code=204)
async def delete_playbook(playbook_id: str, current_user: User = Depends(_GESTAO), db: AsyncSession = Depends(get_db)):
    p = (await db.execute(
        select(AgentAreaPlaybook).where(
            AgentAreaPlaybook.id == uuid.UUID(playbook_id), AgentAreaPlaybook.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Playbook não encontrado.")
    await db.delete(p)
    await db.commit()
