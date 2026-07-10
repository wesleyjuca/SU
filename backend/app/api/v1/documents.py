"""Endpoints para gestão de documentos e petições."""
from fastapi import APIRouter, Depends, Query, UploadFile, File, Form, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Any
import uuid

from app.db.base import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.document import Document, Contract
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
    template_id: str | None = None   # modelo do escritório a usar como base


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    tipo: str | None = None,
    status: str | None = None,
    process_id: str | None = None,
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Document)
        .where(Document.tenant_id == current_user.tenant_id)
        .order_by(desc(Document.created_at))
        .limit(limit)
    )
    if tipo:
        query = query.where(Document.tipo == tipo)
    if status:
        query = query.where(Document.status == status)
    else:
        # Por padrão, documentos arquivados somem da lista (comportamento de "excluir")
        query = query.where(Document.status != "ARQUIVADO")
    if process_id:
        query = query.where(Document.process_id == uuid.UUID(process_id))

    result = await db.execute(query)
    docs = result.scalars().all()
    return [_to_response(d) for d in docs]


@router.post("/upload", status_code=201, response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    titulo: str = Form(...),
    tipo: str = Form("OUTROS"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recebe um arquivo e cria um Document (tenant-scoped). O binário é
    guardado como data URL base64 em `arquivo_url`; texto simples é extraído
    para `conteudo_texto`. PDFs/imagens ficam para o fluxo de OCR."""
    import base64
    import hashlib

    contents = await file.read()
    MAX_BYTES = 10 * 1024 * 1024  # 10MB
    if len(contents) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="Arquivo muito grande. Máximo 10MB.")
    if not contents:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    content_type = file.content_type or "application/octet-stream"
    sha256 = hashlib.sha256(contents).hexdigest()
    data_url = f"data:{content_type};base64," + base64.b64encode(contents).decode()

    # Extrai texto apenas para tipos textuais simples; o resto vai para OCR.
    conteudo_texto = None
    if content_type.startswith("text/") or content_type in ("application/json", "application/xml"):
        conteudo_texto = contents.decode("utf-8", errors="ignore") or None

    doc = Document(
        tipo=tipo,
        titulo=titulo,
        conteudo_texto=conteudo_texto,
        arquivo_url=data_url,
        arquivo_hash=sha256,
        status="RASCUNHO",
        gerado_por_ia=False,
        created_by=current_user.id,
        tenant_id=current_user.tenant_id,
        metadata_json={
            "filename": file.filename,
            "content_type": content_type,
            "size_bytes": len(contents),
        },
    )
    db.add(doc)
    await db.flush()
    return _to_response(doc)


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(doc_id),
            Document.tenant_id == current_user.tenant_id,
        )
    )
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
    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(doc_id),
            Document.tenant_id == current_user.tenant_id,
        )
    )
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


class DocumentUpdate(BaseModel):
    titulo: str | None = None
    status: str | None = None
    conteudo_html: str | None = None
    conteudo_texto: str | None = None


@router.put("/{doc_id}", response_model=DocumentResponse)
async def update_document(
    doc_id: str,
    body: DocumentUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(doc_id),
            Document.tenant_id == current_user.tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Documento", doc_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(doc, field, value)
    await db.flush()

    # Documento aprovado/protocolado → indexa (em background) no RAG do escritório,
    # alimentando a Pesquisa Jurídica. Idempotente e isolado por tenant.
    if doc.status in ("APROVADO", "PROTOCOLADO"):
        texto = doc.conteudo_texto or doc.conteudo_html or ""
        if texto.strip():
            from app.rag.auto_ingest import auto_ingest_document
            background_tasks.add_task(
                auto_ingest_document, doc.id, doc.tenant_id, doc.titulo, doc.tipo, texto, doc.client_id,
            )
    return _to_response(doc)


@router.delete("/{doc_id}", status_code=204)
async def archive_document(
    doc_id: str,
    hard: bool = Query(default=False, description="true = exclusão permanente (remove do banco)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(doc_id),
            Document.tenant_id == current_user.tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Documento", doc_id)
    if hard:
        # Exclusão permanente: remove o Contract associado (se houver) e o Document.
        # As demais relações (versions/petition) têm ondelete=CASCADE.
        contract = (await db.execute(
            select(Contract).where(Contract.document_id == doc.id)
        )).scalar_one_or_none()
        if contract:
            await db.delete(contract)
        await db.delete(doc)
    else:
        doc.status = "ARQUIVADO"
    await db.flush()


@router.get("/{doc_id}/download")
async def download_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response as FastAPIResponse
    from app.utils.pdf_builder import build_petition_pdf

    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(doc_id),
            Document.tenant_id == current_user.tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Documento", doc_id)
    content = doc.conteudo_html or doc.conteudo_texto or ""

    # Timbrado do escritório (Personalização → Timbrado); sem config, padrão AFJ.
    letterhead = None
    try:
        from app.models.tenant import TenantConfig
        cfg = (await db.execute(
            select(TenantConfig).where(TenantConfig.tenant_id == current_user.tenant_id)
        )).scalar_one_or_none()
        if cfg:
            letterhead = dict((cfg.document_templates or {}).get("letterhead", {}))
            if cfg.logo_url:
                letterhead["logo_data_url"] = cfg.logo_url
    except Exception:
        letterhead = None

    pdf_bytes = build_petition_pdf(
        title=doc.titulo,
        content_html=content,
        metadata={"status": doc.status, "versao": doc.versao},
        letterhead=letterhead,
    )
    return FastAPIResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{doc.titulo[:50]}.pdf"'},
    )


class VersionCreate(BaseModel):
    conteudo_html: str
    change_summary: str | None = None


@router.post("/{doc_id}/versions", status_code=201)
async def create_version(
    doc_id: str,
    body: VersionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.document import DocumentVersion
    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(doc_id),
            Document.tenant_id == current_user.tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Documento", doc_id)
    doc.versao += 1
    doc.conteudo_html = body.conteudo_html
    version = DocumentVersion(
        document_id=doc.id,
        versao=doc.versao,
        conteudo_html=body.conteudo_html,
        changed_by=current_user.id,
        change_summary=body.change_summary,
    )
    db.add(version)
    await db.flush()
    return {"document_id": doc_id, "versao": doc.versao, "version_id": str(version.id)}


class ContractCreate(BaseModel):
    client_id: str | None = None
    tipo: str = "HONORARIOS"
    titulo: str
    descricao: str | None = None
    conteudo: str | None = None          # corpo/minuta do contrato (texto)
    valor_total: float | None = None
    data_inicio: str | None = None
    data_fim: str | None = None
    renovacao_auto: bool = False


@router.post("/contracts/create", status_code=201)
async def create_contract(
    body: ContractCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cria um contrato (Document tipo=CONTRATO + Contract associado)."""
    from datetime import datetime
    # Persiste o conteúdo informado (ou a descrição) para o contrato não nascer vazio
    conteudo = (body.conteudo or body.descricao or "").strip() or None
    doc = Document(
        tipo="CONTRATO",
        titulo=body.titulo,
        conteudo_texto=conteudo,
        status="RASCUNHO",
        gerado_por_ia=False,
        created_by=current_user.id,
        tenant_id=current_user.tenant_id,
    )
    db.add(doc)
    await db.flush()
    contract = Contract(
        document_id=doc.id,
        client_id=uuid.UUID(body.client_id) if body.client_id else None,
        tipo=body.tipo,
        valor_total=body.valor_total,
        data_inicio=datetime.fromisoformat(body.data_inicio) if body.data_inicio else None,
        data_fim=datetime.fromisoformat(body.data_fim) if body.data_fim else None,
        renovacao_auto=body.renovacao_auto,
    )
    db.add(contract)
    await db.flush()
    return {"id": str(doc.id), "titulo": doc.titulo, "status": doc.status, "tipo": doc.tipo}


class ContractGenerateRequest(BaseModel):
    instrucoes: str | None = None


@router.post("/contracts/{doc_id}/generate")
async def generate_contract_content(
    doc_id: str,
    body: ContractGenerateRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Gera a minuta do contrato com IA e grava no documento (usa BYOK do usuário,
    se configurado). Retorna o conteúdo para edição — não cria aprovação."""
    from app.integrations.anthropic_client import call_claude, AFJ_LEGAL_SYSTEM_PROMPT
    from app.integrations.byok import user_ai_creds

    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(doc_id),
            Document.tenant_id == current_user.tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Documento", doc_id)

    contract = (await db.execute(
        select(Contract).where(Contract.document_id == doc.id)
    )).scalar_one_or_none()

    tipo = (contract.tipo if contract else None) or "HONORARIOS"
    valor = (contract.valor_total if contract else None)
    dados = [
        f"Título: {doc.titulo}",
        f"Tipo: {tipo.replace('_', ' ').title()}",
    ]
    if valor:
        dados.append(f"Valor total: R$ {valor}")
    if body and body.instrucoes:
        dados.append(f"Instruções: {body.instrucoes}")
    if doc.conteudo_texto:
        dados.append(f"Rascunho/observações atuais: {doc.conteudo_texto[:1000]}")

    system = AFJ_LEGAL_SYSTEM_PROMPT + (
        "\nTAREFA: Geração de contratos jurídicos.\n"
        "- Linguagem clara e tecnicamente precisa\n"
        "- Inclua: objeto, qualificação das partes, honorários e pagamento, prazo, "
        "obrigações das partes, rescisão, confidencialidade, foro (Fortaleza/CE)\n"
        "- Nunca omita cláusulas de proteção ao escritório\n"
        "- Estrutura numerada com títulos em maiúsculas"
    )
    prompt = (
        "Gere um contrato completo para o escritório AFJ Advogados com base nos dados:\n\n"
        + "\n".join(dados)
    )

    from app.services.ai_budget import enforce_budget
    await enforce_budget(db, current_user.id, current_user.tenant_id)

    async with user_ai_creds(db, current_user.id, "manage_contract"):
        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            max_tokens=4000,
            temperature=0.1,
        )

    doc.conteudo_texto = content
    doc.gerado_por_ia = True
    await db.flush()
    return {
        "id": str(doc.id),
        "conteudo": content,
        "tokens_used": input_t + output_t,
        "cost_usd": cost,
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
    from app.models.agent_run import AgentRun
    from app.models.document import PetitionTemplate
    from datetime import datetime
    from decimal import Decimal

    instrucoes = body.instrucoes or ""
    # Se um modelo do escritório foi escolhido, usa seu conteúdo como base para a IA.
    if body.template_id:
        tpl = (await db.execute(
            select(PetitionTemplate).where(
                PetitionTemplate.id == uuid.UUID(body.template_id),
                PetitionTemplate.tenant_id == current_user.tenant_id,
            )
        )).scalar_one_or_none()
        if tpl:
            instrucoes = (
                "Use o MODELO DE PETIÇÃO do escritório abaixo como base "
                "(mantenha estrutura, cláusulas-padrão e substitua os marcadores):\n\n"
                f"===== MODELO: {tpl.nome} =====\n{tpl.conteudo}\n===== FIM DO MODELO =====\n\n"
                + (f"Instruções específicas do caso: {instrucoes}" if instrucoes else "")
            )

    ctx = AgentContext(
        triggered_by=current_user.id,
        task_type="generate_petition",
        task_input={
            "tipo_peticao": body.tipo_peticao,
            "instrucoes": instrucoes,
            "processo": body.processo or {},
        },
        process_id=uuid.UUID(body.process_id) if body.process_id else None,
        client_id=uuid.UUID(body.client_id) if body.client_id else None,
    )

    # Criar AgentRun para que o frontend consiga fazer polling pelo run_id
    run_id = ctx.run_id
    agent_run = AgentRun(
        id=run_id,
        agent_name="petition_agent",
        trigger_type="MANUAL",
        triggered_by=current_user.id,
        input_data=ctx.task_input,
        status="RUNNING",
        tenant_id=current_user.tenant_id,
    )
    db.add(agent_run)
    await db.flush()

    from app.integrations.byok import user_ai_creds

    from app.services.ai_budget import enforce_budget
    await enforce_budget(db, current_user.id, current_user.tenant_id)

    agent = PetitionAgent(db=db)
    async with user_ai_creds(db, current_user.id, "generate_petition"):
        result = await agent.run(ctx)

    # Atualizar AgentRun com resultado (commit via get_db dependency ao final)
    agent_run.status = result.status.value
    agent_run.output_data = result.output
    agent_run.completed_at = datetime.utcnow()
    agent_run.tokens_used = result.tokens_used or None
    agent_run.cost_usd = Decimal(str(result.cost_usd)) if result.cost_usd else None
    agent_run.requires_approval = result.needs_approval

    return {
        "run_id": str(run_id),
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
    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(doc_id),
            Document.tenant_id == current_user.tenant_id,
        )
    )
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
    from app.integrations.byok import user_ai_creds

    from app.services.ai_budget import enforce_budget
    await enforce_budget(db, current_user.id, current_user.tenant_id)

    agent = ReviewAgent(db=db)
    async with user_ai_creds(db, current_user.id, "review_document"):
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
