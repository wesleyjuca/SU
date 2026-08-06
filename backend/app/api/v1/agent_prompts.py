"""Config editável dos prompts/anexos dos agentes nativos (Fase 140.1) —
SUPERADMIN. Registrado fora do bloco try/except que envolve agents.router
(app/api/v1/router.py) — continua funcionando mesmo se o grafo LangGraph
falhar ao montar."""
import base64
import hashlib
import uuid

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel

from app.db.base import get_db
from app.dependencies import require_role
from app.models.user import User
from app.models.agent_prompt import AgentPromptConfig, AgentPromptVersion, AgentAttachment
from app.agents.prompt_registry import AGENT_PROMPT_SLOTS, resolve_default_prompt
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/agents", tags=["agent-prompts"])

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


def _validar_agente(name: str) -> None:
    if name not in AGENT_PROMPT_SLOTS:
        raise HTTPException(status_code=404, detail="Agente desconhecido.")


def _validar_slot(name: str, slot: str) -> None:
    slots = {s["slot"] for s in AGENT_PROMPT_SLOTS.get(name, [])}
    if slot not in slots:
        raise HTTPException(status_code=404, detail=f"Slot '{slot}' não existe para o agente '{name}'.")


def _default_text_para_slot(name: str, slot: str) -> str | None:
    """Resolve o texto padrão (não o override) do slot, pra o SUPERADMIN ver
    o que está editando mesmo sem nenhum override salvo ainda."""
    for s in AGENT_PROMPT_SLOTS.get(name, []):
        if s["slot"] == slot:
            default_ref = s.get("default_ref")
            return resolve_default_prompt(default_ref) if default_ref else None
    return None


class PromptResponse(BaseModel):
    agent_name: str
    slot: str
    prompt_text: str | None  # None = sem override — ver default_text pro texto em vigor
    default_text: str | None  # texto padrão hardcoded, sempre presente pra agentes com LLM
    versao: int
    updated_by: str | None
    updated_at: str | None


class PromptUpdateRequest(BaseModel):
    prompt_text: str | None
    change_summary: str | None = None


class PromptVersionResponse(BaseModel):
    id: str
    versao: int
    prompt_text: str | None
    changed_by: str | None
    change_summary: str | None
    created_at: str


class AttachmentResponse(BaseModel):
    id: str
    filename: str
    content_type: str | None
    size_bytes: int | None
    has_extracted_text: bool
    uploaded_by: str | None
    created_at: str


@router.get("/{name}/prompt-slots")
async def get_prompt_slots(name: str, current_user: User = Depends(require_role("SUPERADMIN"))):
    _validar_agente(name)
    return {"agent_name": name, "slots": AGENT_PROMPT_SLOTS[name]}


@router.get("/{name}/prompt", response_model=PromptResponse)
async def get_agent_prompt(
    name: str,
    slot: str = "primary",
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    _validar_agente(name)
    _validar_slot(name, slot)
    default_text = _default_text_para_slot(name, slot)
    row = (await db.execute(
        select(AgentPromptConfig).where(AgentPromptConfig.agent_name == name, AgentPromptConfig.prompt_slot == slot)
    )).scalar_one_or_none()
    if not row:
        return PromptResponse(
            agent_name=name, slot=slot, prompt_text=None, default_text=default_text,
            versao=0, updated_by=None, updated_at=None,
        )
    return PromptResponse(
        agent_name=name, slot=slot, prompt_text=row.prompt_text, default_text=default_text, versao=row.versao,
        updated_by=str(row.updated_by) if row.updated_by else None,
        updated_at=row.updated_at.isoformat(),
    )


@router.put("/{name}/prompt", response_model=PromptResponse)
async def update_agent_prompt(
    name: str,
    body: PromptUpdateRequest,
    slot: str = "primary",
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Sobrescreve o prompt (ou volta ao default se prompt_text=None). Sempre
    grava snapshot do valor ANTERIOR em AgentPromptVersion antes — mesmo
    padrão de PUT /documents/{doc_id}."""
    _validar_agente(name)
    _validar_slot(name, slot)
    row = (await db.execute(
        select(AgentPromptConfig).where(AgentPromptConfig.agent_name == name, AgentPromptConfig.prompt_slot == slot)
    )).scalar_one_or_none()
    if not row:
        row = AgentPromptConfig(agent_name=name, prompt_slot=slot, prompt_text=None, versao=1)
        db.add(row)
        await db.flush()

    db.add(AgentPromptVersion(
        config_id=row.id, versao=row.versao, prompt_text=row.prompt_text,
        changed_by=current_user.id, change_summary=body.change_summary,
    ))
    row.prompt_text = body.prompt_text
    row.versao += 1
    row.updated_by = current_user.id
    await db.flush()
    return PromptResponse(
        agent_name=name, slot=slot, prompt_text=row.prompt_text,
        default_text=_default_text_para_slot(name, slot), versao=row.versao,
        updated_by=str(current_user.id), updated_at=row.updated_at.isoformat(),
    )


@router.get("/{name}/prompt/versions", response_model=list[PromptVersionResponse])
async def list_prompt_versions(
    name: str,
    slot: str = "primary",
    limit: int = 20,
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    _validar_agente(name)
    _validar_slot(name, slot)
    config = (await db.execute(
        select(AgentPromptConfig).where(AgentPromptConfig.agent_name == name, AgentPromptConfig.prompt_slot == slot)
    )).scalar_one_or_none()
    if not config:
        return []
    rows = (await db.execute(
        select(AgentPromptVersion)
        .where(AgentPromptVersion.config_id == config.id)
        .order_by(desc(AgentPromptVersion.versao))
        .limit(limit)
    )).scalars().all()
    return [PromptVersionResponse(
        id=str(v.id), versao=v.versao, prompt_text=v.prompt_text,
        changed_by=str(v.changed_by) if v.changed_by else None,
        change_summary=v.change_summary, created_at=v.created_at.isoformat(),
    ) for v in rows]


@router.get("/{name}/attachments", response_model=list[AttachmentResponse])
async def list_attachments(
    name: str,
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    _validar_agente(name)
    rows = (await db.execute(
        select(AgentAttachment).where(AgentAttachment.agent_name == name).order_by(desc(AgentAttachment.created_at))
    )).scalars().all()
    return [AttachmentResponse(
        id=str(a.id), filename=a.filename, content_type=a.content_type, size_bytes=a.size_bytes,
        has_extracted_text=bool(a.extracted_text),
        uploaded_by=str(a.uploaded_by) if a.uploaded_by else None, created_at=a.created_at.isoformat(),
    ) for a in rows]


@router.post("/{name}/attachments", status_code=201, response_model=AttachmentResponse)
async def upload_attachment(
    name: str,
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Mesmo padrão de POST /documents/upload: base64 data-URL em Text,
    SHA-256, limite de 10MB, extração de texto só pra tipos textuais
    simples (PDF/imagem fica armazenado mas fora do contexto do prompt
    nesta fase — mesmo gap que documentos já têm com OCR pendente)."""
    _validar_agente(name)
    contents = await file.read()
    if len(contents) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=400, detail="Arquivo muito grande. Máximo 10MB.")
    if not contents:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    content_type = file.content_type or "application/octet-stream"
    sha256 = hashlib.sha256(contents).hexdigest()
    data_url = f"data:{content_type};base64," + base64.b64encode(contents).decode()
    extracted_text = None
    if content_type.startswith("text/") or content_type in ("application/json", "application/xml"):
        extracted_text = contents.decode("utf-8", errors="ignore") or None
    att = AgentAttachment(
        agent_name=name, filename=file.filename or "arquivo", content_type=content_type,
        size_bytes=len(contents), data_url=data_url, extracted_text=extracted_text,
        sha256=sha256, uploaded_by=current_user.id,
    )
    db.add(att)
    await db.flush()
    return AttachmentResponse(
        id=str(att.id), filename=att.filename, content_type=att.content_type, size_bytes=att.size_bytes,
        has_extracted_text=bool(att.extracted_text), uploaded_by=str(current_user.id),
        created_at=att.created_at.isoformat(),
    )


@router.delete("/{name}/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    name: str,
    attachment_id: str,
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    _validar_agente(name)
    row = (await db.execute(
        select(AgentAttachment).where(AgentAttachment.id == uuid.UUID(attachment_id), AgentAttachment.agent_name == name)
    )).scalar_one_or_none()
    if not row:
        raise NotFoundError("AgentAttachment", attachment_id)
    await db.delete(row)
    await db.flush()
