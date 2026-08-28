"""Endpoints para gestão de documentos e petições."""
from fastapi import APIRouter, Depends, Query, UploadFile, File, Form, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel, Field
from typing import Any
import uuid

from app.db.base import get_db
from app.dependencies import get_current_user, require_role
from app.models.user import User
from app.models.document import Document, Contract
from app.models.client import Client
from app.models.process import LegalProcess
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/documents", tags=["documents"])


async def _validar_client_id(db: AsyncSession, client_id: str | None, tenant_id) -> uuid.UUID | None:
    """Garante que o client_id (se informado) pertence ao tenant — evita
    vincular documento/contrato/petição ao cliente de outro escritório."""
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
    vincular documento/petição ao processo de outro escritório."""
    if not process_id:
        return None
    pid = uuid.UUID(process_id)
    existe = (await db.execute(
        select(LegalProcess.id).where(LegalProcess.id == pid, LegalProcess.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not existe:
        raise HTTPException(status_code=404, detail="Processo não encontrado.")
    return pid


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
    tem_texto: bool = False
    tem_arquivo_original: bool = False
    ocr_status: str | None = None
    protocolado_em: str | None = None
    follow_up_dias: int | None = None
    follow_up_alertado: bool = False


class GeneratePetitionRequest(BaseModel):
    tipo_peticao: str
    process_id: str | None = None
    client_id: str | None = None
    instrucoes: str | None = Field(default=None, max_length=4000)
    processo: dict[str, Any] | None = None
    template_id: str | None = None   # modelo do escritório a usar como base


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    tipo: str | None = None,
    status: str | None = None,
    process_id: str | None = None,
    client_id: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Document)
        .where(Document.tenant_id == current_user.tenant_id)
        .order_by(desc(Document.created_at))
        .offset(offset)
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
    if client_id:
        query = query.where(Document.client_id == uuid.UUID(client_id))

    result = await db.execute(query)
    docs = result.scalars().all()
    return [_to_response(d) for d in docs]


class DocumentCreate(BaseModel):
    titulo: str
    tipo: str = "OUTROS"
    conteudo_texto: str | None = None
    conteudo_html: str | None = None
    process_id: str | None = None
    client_id: str | None = None


@router.post("", status_code=201, response_model=DocumentResponse)
async def create_document(
    body: DocumentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cria um documento manual (sem arquivo) — texto/HTML digitado no app.

    Nasce como RASCUNHO; a promoção a APROVADO/PROTOCOLADO segue o gate de papel
    do `PUT /{id}` (invariante HITL)."""
    titulo = (body.titulo or "").strip()
    if not titulo:
        raise HTTPException(status_code=422, detail="Informe o título do documento.")
    doc = Document(
        tipo=body.tipo or "OUTROS",
        titulo=titulo,
        conteudo_texto=body.conteudo_texto,
        conteudo_html=body.conteudo_html,
        status="RASCUNHO",
        gerado_por_ia=False,
        created_by=current_user.id,
        tenant_id=current_user.tenant_id,
        process_id=await _validar_process_id(db, body.process_id, current_user.tenant_id),
        client_id=await _validar_client_id(db, body.client_id, current_user.tenant_id),
    )
    db.add(doc)
    await db.flush()
    return _to_response(doc)


@router.post("/upload", status_code=201, response_model=DocumentResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    titulo: str = Form(...),
    tipo: str = Form("OUTROS"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recebe um arquivo e cria um Document (tenant-scoped). Se object storage
    S3-compatível estiver configurado (Fase 141), o binário vai pra lá e só a
    key fica gravada; senão, segue o caminho legado (data URL base64 em
    `arquivo_url`). Texto simples é extraído para `conteudo_texto`. PDFs/
    imagens ficam para o fluxo de OCR."""
    import base64
    import hashlib

    from app.integrations import object_storage

    contents = await file.read()
    MAX_BYTES = 10 * 1024 * 1024  # 10MB
    if len(contents) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="Arquivo muito grande. Máximo 10MB.")
    if not contents:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    content_type = file.content_type or "application/octet-stream"
    sha256 = hashlib.sha256(contents).hexdigest()

    # Extrai texto apenas para tipos textuais simples; o resto vai para OCR.
    conteudo_texto = None
    if content_type.startswith("text/") or content_type in ("application/json", "application/xml"):
        conteudo_texto = contents.decode("utf-8", errors="ignore") or None

    metadata_json = {
        "filename": file.filename,
        "content_type": content_type,
        "size_bytes": len(contents),
    }
    # PDFs/imagens sem texto extraído inline entram na fila de OCR.
    ocr_pending = _needs_ocr(content_type) and not conteudo_texto
    if ocr_pending:
        metadata_json["ocr"] = {"status": "PENDENTE"}

    doc_id = uuid.uuid4()
    arquivo_url = None
    storage_key = None
    if object_storage.is_configured():
        try:
            storage_key = await object_storage.upload_bytes(
                tenant_id=current_user.tenant_id, document_id=doc_id,
                filename=file.filename or "arquivo", content_type=content_type, data=contents,
            )
        except object_storage.ObjectStorageError:
            raise HTTPException(status_code=502, detail="Falha ao enviar o arquivo para o armazenamento. Tente novamente.")
    else:
        arquivo_url = f"data:{content_type};base64," + base64.b64encode(contents).decode()

    doc = Document(
        id=doc_id,
        tipo=tipo,
        titulo=titulo,
        conteudo_texto=conteudo_texto,
        arquivo_url=arquivo_url,
        arquivo_storage_key=storage_key,
        arquivo_mimetype=content_type,
        arquivo_size_bytes=len(contents),
        arquivo_hash=sha256,
        status="RASCUNHO",
        gerado_por_ia=False,
        created_by=current_user.id,
        tenant_id=current_user.tenant_id,
        metadata_json=metadata_json,
    )
    db.add(doc)
    await db.flush()

    # Dispara o OCR em background (Celery, com fallback in-process). O upload
    # já retorna 201 — o texto extraído aparece quando o worker conclui.
    if ocr_pending:
        _dispatch_ocr(doc.id, current_user.tenant_id, background_tasks)

    return _to_response(doc)


@router.post("/{doc_id}/ocr", status_code=202)
async def trigger_ocr(
    doc_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """(Re)processa o OCR de um documento sob demanda (tenant-scoped)."""
    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(doc_id),
            Document.tenant_id == current_user.tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Documento", doc_id)

    meta = dict(doc.metadata_json or {})
    meta["ocr"] = {"status": "PENDENTE"}
    doc.metadata_json = meta
    await db.flush()

    _dispatch_ocr(doc.id, current_user.tenant_id, background_tasks)
    return {"document_id": doc_id, "ocr_status": "PENDENTE"}


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
    # Fase 205.1 — dias de prazo pra follow-up de petição protocolada sem
    # resposta da corte; NULL desativa o alerta. `0` limpa (frontend manda
    # string vazia -> None; aqui é só o valor numérico já validado).
    follow_up_dias: int | None = None


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

    updates = body.model_dump(exclude_none=True)
    # Fase 130 — invariante HITL (CLAUDE.md: "a ação não é executada até
    # aprovação humana... nunca bypassar"). Documento gerado por IA só pode
    # sair de RASCUNHO/PENDENTE via /approvals/{id}/resolve — essa rota
    # genérica de PUT permitia qualquer ADVOGADO/SOCIO/ADMIN aprovar direto,
    # pulando a fila de revisão inteira (verificação de citação, aviso de
    # truncamento, justificativa de rejeição). Documentos NÃO gerados por IA
    # (upload manual) continuam livres — não há ação de IA nenhuma a proteger.
    if updates.get("status") in ("APROVADO", "PROTOCOLADO") and doc.gerado_por_ia:
        raise HTTPException(
            status_code=403,
            detail="Documentos gerados por IA só podem ser aprovados/protocolados pelo fluxo de "
                   "aprovação (Aprovações pendentes) — não é permitido via edição direta.",
        )

    # Se o conteúdo vai mudar, guarda o estado ANTERIOR como versão (histórico),
    # antes de sobrescrever. Só quando havia algum conteúdo e ele de fato muda.
    muda_conteudo = (
        ("conteudo_texto" in updates and updates["conteudo_texto"] != doc.conteudo_texto)
        or ("conteudo_html" in updates and updates["conteudo_html"] != doc.conteudo_html)
    )
    if muda_conteudo and (doc.conteudo_texto or doc.conteudo_html):
        from app.models.document import DocumentVersion
        db.add(DocumentVersion(
            document_id=doc.id,
            versao=doc.versao,
            conteudo_html=doc.conteudo_html,
            conteudo_texto=doc.conteudo_texto,
            changed_by=current_user.id,
            change_summary="Edição",
        ))
        doc.versao += 1

    # Fase 205.1 — carimba protocolado_em na transição pra PROTOCOLADO (uma
    # vez só, separado de updated_at que muda a cada edição posterior).
    entrando_em_protocolado = updates.get("status") == "PROTOCOLADO" and doc.status != "PROTOCOLADO"

    for field, value in updates.items():
        setattr(doc, field, value)
    if entrando_em_protocolado:
        from datetime import datetime, timezone
        doc.protocolado_em = datetime.now(timezone.utc)
        doc.follow_up_alertado = False
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
        # Exclusão PERMANENTE é restrita a ADMIN/SÓCIO (arquivar continua livre).
        if current_user.role not in ("ADMIN", "SUPERADMIN", "SOCIO"):
            raise HTTPException(
                status_code=403,
                detail="Exclusão permanente é restrita a administradores e sócios. Use Arquivar.",
            )
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
            from app.services.letterhead import resolve_logo_data_url
            logo_data_url = await resolve_logo_data_url(cfg)
            if logo_data_url:
                letterhead["logo_data_url"] = logo_data_url
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


@router.get("/{doc_id}/original")
async def download_document_original(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Serve os bytes originalmente enviados no upload (Fase 141) — ao
    contrário de `/download`, que sempre re-renderiza um PDF a partir do
    texto extraído. Funciona tanto pra documentos migrados pro object
    storage quanto pro caminho legado (base64 inline)."""
    from fastapi.responses import Response as FastAPIResponse

    from app.integrations import object_storage
    from app.utils.data_url import parse_data_url

    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(doc_id),
            Document.tenant_id == current_user.tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Documento", doc_id)

    filename = (doc.metadata_json or {}).get("filename") or f"{doc.titulo[:50]}"

    if doc.arquivo_storage_key:
        try:
            raw = await object_storage.get_bytes(doc.arquivo_storage_key)
        except object_storage.ObjectStorageError:
            raise HTTPException(status_code=502, detail="Falha ao recuperar o arquivo original.")
        content_type = doc.arquivo_mimetype or "application/octet-stream"
    else:
        b64, ct = parse_data_url(doc.arquivo_url or "")
        if not b64:
            raise HTTPException(status_code=404, detail="Este documento não possui um arquivo original enviado.")
        import base64
        raw = base64.b64decode(b64)
        content_type = doc.arquivo_mimetype or ct or "application/octet-stream"

    return FastAPIResponse(
        content=raw,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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


@router.get("/{doc_id}/versions")
async def list_versions(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Histórico de versões do documento (mais recente primeiro)."""
    from app.models.document import DocumentVersion
    doc = (await db.execute(
        select(Document.id).where(
            Document.id == uuid.UUID(doc_id), Document.tenant_id == current_user.tenant_id
        )
    )).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Documento", doc_id)

    rows = (await db.execute(
        select(DocumentVersion, User.full_name)
        .outerjoin(User, User.id == DocumentVersion.changed_by)
        .where(DocumentVersion.document_id == doc)
        .order_by(desc(DocumentVersion.versao))
    )).all()
    return [
        {
            "id": str(v.id),
            "versao": v.versao,
            "change_summary": v.change_summary,
            "autor": nome,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v, nome in rows
    ]


@router.post("/{doc_id}/versions/{version_id}/restore", response_model=DocumentResponse)
async def restore_version(
    doc_id: str,
    version_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Restaura o conteúdo de uma versão anterior (guarda o estado atual como nova versão)."""
    from app.models.document import DocumentVersion
    doc = (await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(doc_id), Document.tenant_id == current_user.tenant_id
        )
    )).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Documento", doc_id)
    ver = (await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.id == uuid.UUID(version_id),
            DocumentVersion.document_id == doc.id,
        )
    )).scalar_one_or_none()
    if not ver:
        raise NotFoundError("Versão", version_id)

    # Snapshot do estado atual antes de restaurar, para não perder o histórico.
    db.add(DocumentVersion(
        document_id=doc.id,
        versao=doc.versao,
        conteudo_html=doc.conteudo_html,
        conteudo_texto=doc.conteudo_texto,
        changed_by=current_user.id,
        change_summary=f"Restaurado da v{ver.versao}",
    ))
    doc.versao += 1
    doc.conteudo_html = ver.conteudo_html
    doc.conteudo_texto = ver.conteudo_texto
    await db.flush()
    return _to_response(doc)


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
        client_id=await _validar_client_id(db, body.client_id, current_user.tenant_id),
        tipo=body.tipo,
        valor_total=body.valor_total,
        data_inicio=datetime.fromisoformat(body.data_inicio) if body.data_inicio else None,
        data_fim=datetime.fromisoformat(body.data_fim) if body.data_fim else None,
        renovacao_auto=body.renovacao_auto,
    )
    db.add(contract)
    await db.flush()
    return {"id": str(doc.id), "titulo": doc.titulo, "status": doc.status, "tipo": doc.tipo}


class Signatario(BaseModel):
    email: str
    nome: str


class ContractSendSignature(BaseModel):
    # Fase 244 (achado do diagnóstico de cadastros) — multi-signatário. Os
    # campos email/nome antigos continuam aceitos (contrato com 1 único
    # signatário, caso mais comum) — quando `signatarios` vem preenchido,
    # ele é a fonte de verdade e os campos soltos são ignorados.
    email: str | None = None
    nome: str | None = None
    signatarios: list[Signatario] | None = None


@router.post("/contracts/{doc_id}/enviar-assinatura")
async def enviar_contrato_assinatura(
    doc_id: str,
    body: ContractSendSignature,
    current_user: User = Depends(require_role("ADVOGADO", "GESTOR", "SOCIO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Envia o contrato para assinatura eletrônica via Clicksign (Integrações).

    Ação humana com gate de papel (o advogado é o humano no circuito); o
    signatário recebe o e-mail do Clicksign e o webhook de retorno marca o
    contrato como ASSINADO após verificação na API do provedor."""
    from app.services.esign import enviar_para_assinatura

    doc = (await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(doc_id),
            Document.tenant_id == current_user.tenant_id,
            Document.tipo == "CONTRATO",
        )
    )).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Contrato não encontrado.")
    if not (doc.conteudo_html or doc.conteudo_texto):
        raise HTTPException(status_code=422, detail="Contrato sem conteúdo — gere ou escreva a minuta antes de enviar.")
    contract = (await db.execute(
        select(Contract).where(Contract.document_id == doc.id)
    )).scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="Registro do contrato não encontrado.")
    if contract.status == "ASSINADO":
        raise HTTPException(status_code=422, detail="Contrato já assinado.")

    if body.signatarios:
        signatarios = [{"email": s.email.strip(), "nome": s.nome.strip()} for s in body.signatarios]
    elif body.email and body.nome:
        signatarios = [{"email": body.email.strip(), "nome": body.nome.strip()}]
    else:
        raise HTTPException(status_code=422, detail="Informe ao menos 1 signatário (email/nome).")

    result = await enviar_para_assinatura(db, current_user.tenant_id, doc, contract, signatarios)
    nomes = ", ".join(s["email"] for s in signatarios)
    return {
        "message": f"Contrato enviado para assinatura de {nomes} via Clicksign.",
        **result,
        "status": contract.status,
    }


class ContractGenerateRequest(BaseModel):
    instrucoes: str | None = Field(default=None, max_length=4000)


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
            "_tenant_id": str(current_user.tenant_id),
        },
        tenant_id=current_user.tenant_id,
        process_id=await _validar_process_id(db, body.process_id, current_user.tenant_id),
        client_id=await _validar_client_id(db, body.client_id, current_user.tenant_id),
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

    # Invariante HITL: este caminho síncrono (o que a UI usa) também alimenta a
    # fila de aprovações — antes só o caminho do worker criava o Approval, e a
    # petição gerada aqui nunca aparecia em /aprovacoes.
    approval_id = None
    if result.status.value == "AWAITING_APPROVAL" or result.needs_approval:
        from app.services.approval import create_approval_from_state
        approval_id = await create_approval_from_state(db, agent_run, {
            "pending_approval": {
                "tipo": "PETICAO",
                "titulo": f"Protocolar petição: {body.tipo_peticao}",
                "descricao": "Petição gerada por IA aguardando revisão e decisão humana.",
                "prioridade": "NORMAL",
            },
            "agent_results": [result],
        })

    return {
        "run_id": str(run_id),
        "status": result.status.value,
        "document_id": result.output.get("document_id"),
        "approval_required": result.approval_required,
        "approval_id": str(approval_id) if approval_id else None,
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


@router.post("/{doc_id}/verificar-citacoes")
async def verificar_citacoes_documento(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extrai referências de lei e de processo do documento e confere cada
    uma na fonte oficial (LexML / DataJud) — sob demanda, não bloqueia
    edição/aprovação."""
    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(doc_id),
            Document.tenant_id == current_user.tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Documento", doc_id)

    tribunal = None
    if doc.process_id:
        tribunal = (await db.execute(
            select(LegalProcess.tribunal).where(
                LegalProcess.id == doc.process_id,
                LegalProcess.tenant_id == current_user.tenant_id,
            )
        )).scalar_one_or_none()

    from app.services.citacao_check import verificar_citacoes
    citacoes = await verificar_citacoes(doc.conteudo_texto or "", tribunal=tribunal)
    return {"document_id": doc_id, "citacoes": citacoes}


def _to_response(d: Document) -> DocumentResponse:
    ocr = (d.metadata_json or {}).get("ocr") if isinstance(d.metadata_json, dict) else None
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
        tem_texto=bool((d.conteudo_texto or "").strip()),
        tem_arquivo_original=bool(d.arquivo_storage_key or (d.arquivo_url or "").startswith("data:")),
        ocr_status=(ocr or {}).get("status") if isinstance(ocr, dict) else None,
        protocolado_em=d.protocolado_em.isoformat() if d.protocolado_em else None,
        follow_up_dias=d.follow_up_dias,
        follow_up_alertado=bool(d.follow_up_alertado),
    )


# Tipos de arquivo que passam por OCR (o resto ou já é texto, ou não é digitalizável).
_OCR_CONTENT_TYPES = ("application/pdf",)


def _needs_ocr(content_type: str) -> bool:
    return content_type == "application/pdf" or content_type.startswith("image/")


def _dispatch_ocr(doc_id, tenant_id, background_tasks: BackgroundTasks) -> None:
    """Aciona o OCR via Celery; se o broker estiver fora, cai no BackgroundTasks
    in-process. O chamador nunca deve falhar por causa disto."""
    doc_id_s, tenant_s = str(doc_id), str(tenant_id) if tenant_id else None
    try:
        from app.workers.tasks.ocr_tasks import ocr_document_task
        ocr_document_task.delay(doc_id_s, tenant_s)
    except Exception:
        from app.workers.tasks.ocr_tasks import run_ocr_inproc
        background_tasks.add_task(run_ocr_inproc, doc_id_s, tenant_s)
