"""Endpoints para gestão de processos judiciais."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel, field_validator
import uuid

from app.db.base import get_db
from app.dependencies import get_current_user, require_role
from app.models.user import User
from app.models.process import LegalProcess, ProcessMovement, ProcessDeadline, ProcessTeamMember, ProcessParty
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/processes", tags=["processes"])


class ProcessCreate(BaseModel):
    numero_cnj: str | None = None
    tribunal: str
    vara: str | None = None
    comarca: str | None = None
    uf: str | None = None
    tipo_acao: str | None = None
    area_direito: str | None = None
    fase: str | None = None
    valor_causa: float | None = None
    client_id: str | None = None
    parte_contraria: str | None = None
    polo: str | None = None
    oab_responsavel: str | None = None
    monitoring_active: bool = True
    desfecho: str | None = None  # EXITO, PARCIAL, ACORDO, DERROTA
    descricao: str | None = None
    responsavel_id: str | None = None       # advogado principal (default: quem cria)
    equipe: list[str] | None = None         # demais advogados do processo


_SITUACOES_VALIDAS = {"ATIVO", "SUSPENSO", "ARQUIVADO", "ENCERRADO"}


class ProcessUpdate(BaseModel):
    """Fase 133 — schema próprio pro PUT, separado de `ProcessCreate`: antes o
    endpoint reaproveitava `ProcessCreate` (que exige `tribunal` e não tem
    `situacao`) — qualquer edição parcial que só quisesse mudar `situacao`
    era silenciosamente ignorada pelo Pydantic (campo não existia no schema),
    e uma edição legítima que omitisse `tribunal` quebraria com 422."""
    numero_cnj: str | None = None
    tribunal: str | None = None
    vara: str | None = None
    comarca: str | None = None
    uf: str | None = None
    tipo_acao: str | None = None
    area_direito: str | None = None
    fase: str | None = None
    situacao: str | None = None
    valor_causa: float | None = None
    client_id: str | None = None
    parte_contraria: str | None = None
    polo: str | None = None
    oab_responsavel: str | None = None
    monitoring_active: bool | None = None
    desfecho: str | None = None
    descricao: str | None = None
    responsavel_id: str | None = None
    equipe: list[str] | None = None

    @field_validator("situacao")
    @classmethod
    def _validar_situacao(cls, v):
        if v is not None and v not in _SITUACOES_VALIDAS:
            raise ValueError(f"situacao inválida. Use: {', '.join(sorted(_SITUACOES_VALIDAS))}")
        return v


class TeamMemberOut(BaseModel):
    id: str
    nome: str
    papel: str


class ProcessResponse(BaseModel):
    id: str
    numero_cnj: str | None
    tribunal: str
    vara: str | None
    comarca: str | None = None
    uf: str | None = None
    tipo_acao: str | None = None
    area_direito: str | None
    fase: str | None = None
    situacao: str
    desfecho: str | None
    valor_causa: float | None
    client_id: str | None
    parte_contraria: str | None = None
    polo: str | None = None
    oab_responsavel: str | None = None
    descricao: str | None = None
    responsavel_id: str | None
    responsavel_nome: str | None = None
    equipe: list[TeamMemberOut] = []
    proximo_prazo_at: str | None
    ultimo_andamento_at: str | None
    monitoring_active: bool
    fonte: str | None = None
    created_at: str


async def _validar_client_id(db: AsyncSession, client_id: str | None, tenant_id) -> uuid.UUID | None:
    """Garante que o client_id (se informado) pertence ao tenant — evita
    vincular o processo ao cliente de outro escritório."""
    if not client_id:
        return None
    from app.models.client import Client
    from fastapi import HTTPException
    cid = uuid.UUID(client_id)
    existe = (await db.execute(
        select(Client.id).where(Client.id == cid, Client.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not existe:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    return cid


async def _validar_advogados_do_tenant(db: AsyncSession, tenant_id, user_ids: list[uuid.UUID]) -> dict:
    """Retorna {id: nome} dos usuários que pertencem ao tenant; 422 se algum não pertencer."""
    if not user_ids:
        return {}
    rows = (await db.execute(
        select(User.id, User.full_name).where(
            User.id.in_(user_ids),
            User.tenant_id == tenant_id,
            User.is_active == True,  # noqa: E712
        )
    )).all()
    found = {r[0]: r[1] for r in rows}
    faltantes = set(user_ids) - set(found)
    if faltantes:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Advogado(s) não encontrado(s) neste escritório.")
    return found


async def _set_team(db: AsyncSession, process: LegalProcess, tenant_id,
                    responsavel_id: uuid.UUID | None, equipe_ids: list[uuid.UUID]) -> None:
    """Define a equipe do processo. O responsável entra como RESPONSAVEL e é
    espelhado em `process.responsavel_id` (retrocompat); os demais, COLABORADOR."""
    todos = list({*(equipe_ids or []), *( [responsavel_id] if responsavel_id else [] )})
    await _validar_advogados_do_tenant(db, tenant_id, todos)

    # substitui a equipe atual
    from sqlalchemy import delete as sa_delete
    await db.execute(sa_delete(ProcessTeamMember).where(ProcessTeamMember.process_id == process.id))
    if responsavel_id:
        process.responsavel_id = responsavel_id
        db.add(ProcessTeamMember(process_id=process.id, user_id=responsavel_id, papel="RESPONSAVEL"))
    for uid in equipe_ids or []:
        if uid != responsavel_id:
            db.add(ProcessTeamMember(process_id=process.id, user_id=uid, papel="COLABORADOR"))
    await db.flush()


async def _to_responses(db: AsyncSession, processes: list[LegalProcess]) -> list[ProcessResponse]:
    """Converte processos em respostas, resolvendo nomes do responsável e da equipe
    em 2 queries (batch) — sem N+1."""
    if not processes:
        return []
    ids = [p.id for p in processes]
    team_rows = (await db.execute(
        select(ProcessTeamMember.process_id, ProcessTeamMember.user_id, ProcessTeamMember.papel, User.full_name)
        .join(User, User.id == ProcessTeamMember.user_id)
        .where(ProcessTeamMember.process_id.in_(ids))
    )).all()
    team_map: dict = {}
    for pid, uid_, papel, nome in team_rows:
        team_map.setdefault(pid, []).append(TeamMemberOut(id=str(uid_), nome=nome, papel=papel))

    resp_ids = {p.responsavel_id for p in processes if p.responsavel_id}
    nomes = {}
    if resp_ids:
        nomes = dict((await db.execute(
            select(User.id, User.full_name).where(User.id.in_(resp_ids))
        )).all())

    out = []
    for p in processes:
        base = _to_response(p)
        base.responsavel_nome = nomes.get(p.responsavel_id)
        base.equipe = team_map.get(p.id, [])
        out.append(base)
    return out


@router.get("/agenda")
async def get_agenda(
    dias: int = Query(default=30, ge=1, le=90),
    mine: bool = Query(default=False, description="Somente prazos dos meus processos/sob minha responsabilidade"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retorna todos os prazos pendentes do tenant com dados do processo, ordenados por data."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc).date()
    cutoff = now + timedelta(days=dias)

    query = (
        select(ProcessDeadline, LegalProcess)
        .join(LegalProcess, ProcessDeadline.process_id == LegalProcess.id)
        .where(
            LegalProcess.tenant_id == current_user.tenant_id,
            ProcessDeadline.status == "PENDENTE",
            ProcessDeadline.data_prazo <= cutoff,
        )
        .order_by(ProcessDeadline.data_prazo.asc())
    )
    if mine or await _confinar_a_equipe(db, current_user):
        from sqlalchemy import or_
        query = query.where(or_(
            ProcessDeadline.responsavel_id == current_user.id,
            _mine_filter(current_user.id),
        ))
    q = await db.execute(query)
    rows = q.all()
    return [
        {
            "id": str(d.id),
            "descricao": d.descricao,
            "tipo": d.tipo,
            "status": d.status,
            "data_prazo": d.data_prazo.isoformat() if d.data_prazo else None,
            "data_fatal": d.data_fatal.isoformat() if d.data_fatal else None,
            "process_id": str(p.id),
            "numero_cnj": p.numero_cnj,
            "tribunal": p.tribunal,
            "area_direito": p.area_direito,
        }
        for d, p in rows
    ]


def _mine_filter(user_id):
    """Processos onde sou o responsável OU estou na equipe (Minha Área)."""
    from sqlalchemy import or_
    return or_(
        LegalProcess.responsavel_id == user_id,
        LegalProcess.id.in_(
            select(ProcessTeamMember.process_id).where(ProcessTeamMember.user_id == user_id)
        ),
    )


# Papéis de gestão sempre veem todo o escritório, mesmo no modo confidencial.
_VE_TUDO_ROLES = {"ADMIN", "SUPERADMIN", "SOCIO", "GESTOR"}


async def _confidencial_ativo(db: AsyncSession, tenant_id) -> bool:
    """Modo confidencial do escritório (TenantConfig.extra_data['modo_confidencial'])."""
    from app.models.tenant import TenantConfig
    if not tenant_id:
        return False
    cfg = (await db.execute(
        select(TenantConfig).where(TenantConfig.tenant_id == tenant_id)
    )).scalar_one_or_none()
    return bool((cfg.extra_data or {}).get("modo_confidencial")) if cfg else False


async def _confinar_a_equipe(db: AsyncSession, current_user: User) -> bool:
    """True quando o usuário deve ver só os processos da sua equipe: modo
    confidencial ligado E papel não-gestão. Gestão (ADMIN/SOCIO/GESTOR) vê tudo."""
    if current_user.role in _VE_TUDO_ROLES:
        return False
    return await _confidencial_ativo(db, current_user.tenant_id)


@router.get("/sincronizacoes")
async def listar_sincronizacoes(
    limit: int = Query(default=20, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Histórico de sincronizações da captura (Fase 72): capturas por OAB e
    varreduras de intimações do escritório + ciclos globais de polling."""
    from sqlalchemy import or_, and_
    from app.models.sync_run import SyncRun

    rows = (await db.execute(
        select(SyncRun).where(
            or_(
                SyncRun.tenant_id == current_user.tenant_id,
                and_(SyncRun.tenant_id.is_(None), SyncRun.tipo == "POLLING"),
            )
        ).order_by(SyncRun.started_at.desc()).limit(limit)
    )).scalars().all()
    return [{
        "id": str(r.id),
        "fonte": r.fonte,
        "tipo": r.tipo,
        "status": r.status,
        "stats": r.stats or {},
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
    } for r in rows]


@router.get("", response_model=list[ProcessResponse])
async def list_processes(
    tribunal: str | None = None,
    area_direito: str | None = None,
    situacao: str | None = None,
    client_id: str | None = None,
    mine: bool = Query(default=False, description="Somente os processos do advogado logado"),
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(LegalProcess)
        .where(LegalProcess.tenant_id == current_user.tenant_id)
        .order_by(LegalProcess.proximo_prazo_at.asc().nulls_last())
        .offset(offset)
        .limit(limit)
    )

    if tribunal:
        query = query.where(LegalProcess.tribunal == tribunal)
    if area_direito:
        query = query.where(LegalProcess.area_direito == area_direito)
    if situacao:
        query = query.where(LegalProcess.situacao == situacao)
    if client_id:
        query = query.where(LegalProcess.client_id == uuid.UUID(client_id))
    if mine or await _confinar_a_equipe(db, current_user):
        query = query.where(_mine_filter(current_user.id))

    result = await db.execute(query)
    processes = result.scalars().all()
    return await _to_responses(db, list(processes))


@router.post("", response_model=ProcessResponse, status_code=201)
async def create_process(
    body: ProcessCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    responsavel = uuid.UUID(body.responsavel_id) if body.responsavel_id else current_user.id
    equipe = [uuid.UUID(e) for e in (body.equipe or [])]

    process = LegalProcess(
        **body.model_dump(exclude_none=True, exclude={"client_id", "responsavel_id", "equipe"}),
        responsavel_id=responsavel,
        tenant_id=current_user.tenant_id,
        client_id=await _validar_client_id(db, body.client_id, current_user.tenant_id),
        fonte="MANUAL",
    )
    db.add(process)
    await db.flush()
    await _set_team(db, process, current_user.tenant_id, responsavel, equipe)
    return (await _to_responses(db, [process]))[0]


@router.get("/{process_id}", response_model=ProcessResponse)
async def get_process(
    process_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LegalProcess).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    process = result.scalar_one_or_none()
    if not process:
        raise NotFoundError("Processo", process_id)
    # Modo confidencial: só a equipe do processo o abre (não vaza existência p/ terceiros).
    if await _confinar_a_equipe(db, current_user):
        na_equipe = (await db.execute(
            select(ProcessTeamMember.id).where(
                ProcessTeamMember.process_id == process.id,
                ProcessTeamMember.user_id == current_user.id,
            )
        )).scalar_one_or_none()
        if process.responsavel_id != current_user.id and not na_equipe:
            raise NotFoundError("Processo", process_id)
    return (await _to_responses(db, [process]))[0]


@router.get("/{process_id}/movements")
async def get_movements(
    process_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    proc_check = await db.execute(
        select(LegalProcess.id).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    if not proc_check.scalar_one_or_none():
        raise NotFoundError("Processo", process_id)
    result = await db.execute(
        select(ProcessMovement)
        .where(ProcessMovement.process_id == uuid.UUID(process_id))
        .order_by(desc(ProcessMovement.data_movimento))
        .limit(limit)
    )
    movements = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "data_movimento": m.data_movimento.isoformat(),
            "descricao": m.descricao,
            "tipo": m.tipo,
            "ai_summary": m.ai_summary,
            "documento_url": m.documento_url,
            "possivel_prazo": bool(m.possivel_prazo),
        }
        for m in movements
    ]


@router.get("/{process_id}/partes")
async def get_partes(
    process_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista as partes do processo (autor, réu, advogados) — populadas pela fonte
    credenciada PDPJ/Escavador/Judit/Jusbrasil (Fase 75) ou cadastradas
    manualmente (Fase 127). Vazio até o processo ter partes."""
    proc_check = await db.execute(
        select(LegalProcess.id).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    if not proc_check.scalar_one_or_none():
        raise NotFoundError("Processo", process_id)
    rows = (await db.execute(
        select(ProcessParty)
        .where(ProcessParty.process_id == uuid.UUID(process_id))
        .order_by(ProcessParty.polo, ProcessParty.tipo)
    )).scalars().all()
    return [
        {
            "id": str(p.id),
            "tipo": p.tipo,
            "nome": p.nome,
            "cpf_cnpj": p.cpf_cnpj,
            "oab": p.oab,
            "polo": p.polo,
            "origem": p.origem,
        }
        for p in rows
    ]


class PartyCreate(BaseModel):
    nome: str
    tipo: str  # AUTOR, REU, ADVOGADO, JUIZ, MP, PARTE
    polo: str | None = None
    cpf_cnpj: str | None = None
    oab: str | None = None


@router.post("/{process_id}/partes", status_code=201)
async def create_parte(
    process_id: str,
    body: PartyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cadastro manual de parte (Fase 127) — alternativa ao sync automático
    (PJe/PDPJ, Escavador, Judit, Jusbrasil) quando nenhum provedor está
    conectado, ou pra corrigir/completar dados importados."""
    proc_check = await db.execute(
        select(LegalProcess.id).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    if not proc_check.scalar_one_or_none():
        raise NotFoundError("Processo", process_id)

    party = ProcessParty(
        process_id=uuid.UUID(process_id),
        tipo=body.tipo[:20],
        nome=body.nome[:500],
        polo=body.polo,
        cpf_cnpj=body.cpf_cnpj,
        oab=body.oab,
        origem="MANUAL",
    )
    db.add(party)
    await db.flush()
    return {
        "id": str(party.id),
        "tipo": party.tipo,
        "nome": party.nome,
        "cpf_cnpj": party.cpf_cnpj,
        "oab": party.oab,
        "polo": party.polo,
        "origem": party.origem,
    }


async def _get_parte_do_tenant(db: AsyncSession, process_id: str, parte_id: str, tenant_id) -> ProcessParty:
    """Confirma que a parte pertence ao processo E que o processo pertence
    ao tenant do usuário — evita IDOR (editar/excluir parte de outro escritório
    passando um process_id qualquer)."""
    row = (await db.execute(
        select(ProcessParty)
        .join(LegalProcess, LegalProcess.id == ProcessParty.process_id)
        .where(
            ProcessParty.id == uuid.UUID(parte_id),
            ProcessParty.process_id == uuid.UUID(process_id),
            LegalProcess.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()
    if not row:
        raise NotFoundError("Parte", parte_id)
    return row


@router.put("/{process_id}/partes/{parte_id}")
async def update_parte(
    process_id: str,
    parte_id: str,
    body: PartyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Edita uma parte (manual ou importada — corrigir um dado errado da
    importação é um caso de uso legítimo, não só cadastro manual)."""
    party = await _get_parte_do_tenant(db, process_id, parte_id, current_user.tenant_id)
    party.tipo = body.tipo[:20]
    party.nome = body.nome[:500]
    party.polo = body.polo
    party.cpf_cnpj = body.cpf_cnpj
    party.oab = body.oab
    await db.flush()
    return {
        "id": str(party.id),
        "tipo": party.tipo,
        "nome": party.nome,
        "cpf_cnpj": party.cpf_cnpj,
        "oab": party.oab,
        "polo": party.polo,
        "origem": party.origem,
    }


@router.delete("/{process_id}/partes/{parte_id}", status_code=204)
async def delete_parte(
    process_id: str,
    parte_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    party = await _get_parte_do_tenant(db, process_id, parte_id, current_user.tenant_id)
    await db.delete(party)
    await db.flush()


@router.get("/{process_id}/deadlines")
async def get_deadlines(
    process_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    proc_check = await db.execute(
        select(LegalProcess.id).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    if not proc_check.scalar_one_or_none():
        raise NotFoundError("Processo", process_id)
    result = await db.execute(
        select(ProcessDeadline)
        .where(
            ProcessDeadline.process_id == uuid.UUID(process_id),
            ProcessDeadline.status == "PENDENTE",
        )
        .order_by(ProcessDeadline.data_prazo.asc())
    )
    deadlines = result.scalars().all()
    return [
        {
            "id": str(d.id),
            "descricao": d.descricao,
            "data_prazo": d.data_prazo.isoformat() if d.data_prazo else None,
            "data_fatal": d.data_fatal.isoformat() if d.data_fatal else None,
            "tipo": d.tipo,
            "status": d.status,
        }
        for d in deadlines
    ]


@router.put("/{process_id}", response_model=ProcessResponse)
async def update_process(
    process_id: str,
    body: ProcessUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LegalProcess).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    process = result.scalar_one_or_none()
    if not process:
        raise NotFoundError("Processo", process_id)
    for field, value in body.model_dump(exclude_none=True, exclude={"responsavel_id", "equipe"}).items():
        if field == "client_id" and value:
            setattr(process, field, await _validar_client_id(db, value, current_user.tenant_id))
        else:
            setattr(process, field, value)
    # Reatribuição de responsável/equipe (opcional no mesmo PUT)
    if body.responsavel_id or body.equipe is not None:
        responsavel = uuid.UUID(body.responsavel_id) if body.responsavel_id else process.responsavel_id
        equipe = [uuid.UUID(e) for e in (body.equipe or [])]
        await _set_team(db, process, current_user.tenant_id, responsavel, equipe)
    await db.flush()
    return (await _to_responses(db, [process]))[0]


class TeamUpdate(BaseModel):
    responsavel_id: str
    equipe: list[str] = []


@router.put("/{process_id}/equipe", response_model=ProcessResponse)
async def set_process_team(
    process_id: str,
    body: TeamUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Define o advogado responsável e a equipe do processo (todos do tenant)."""
    result = await db.execute(
        select(LegalProcess).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    process = result.scalar_one_or_none()
    if not process:
        raise NotFoundError("Processo", process_id)
    await _set_team(
        db, process, current_user.tenant_id,
        uuid.UUID(body.responsavel_id),
        [uuid.UUID(e) for e in body.equipe],
    )
    return (await _to_responses(db, [process]))[0]


@router.post("/{process_id}/atualizar-andamentos")
async def atualizar_andamentos(
    process_id: str,
    # Buscar andamentos no tribunal é ação de trabalho — restrita ao staff jurídico/gestão
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "ADVOGADO", "GESTOR", "PARALEGAL", "ASSISTENTE")),
    db: AsyncSession = Depends(get_db),
):
    """Busca os andamentos do processo no DataJud (API pública, por número CNJ) e
    grava os novos como ProcessMovement. Fonte só de metadados/movimentos — não
    protocola nem executa nada."""
    from datetime import datetime, timezone
    from app.integrations.tribunais.cnj import CNJDataJudClient

    process = (await db.execute(
        select(LegalProcess).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if not process:
        raise NotFoundError("Processo", process_id)
    if not process.numero_cnj:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Processo sem número CNJ — não é possível consultar o tribunal.")

    client = CNJDataJudClient()
    try:
        dados = await client.fetch_processo(process.numero_cnj, process.tribunal)
    except Exception:
        dados = None
    finally:
        await client.close()

    if dados is None:
        process.last_polled_at = datetime.now(timezone.utc)
        await db.commit()
        return {"novos": 0, "fonte_respondeu": False,
                "message": "A fonte pública (DataJud) não respondeu — verifique o acesso à internet do ambiente ou tente mais tarde."}

    # Importador ÚNICO (Fase 72): dedup canônico + possivel_prazo + notificação
    # da equipe — mesmo caminho do agente de polling e da captura por OAB.
    from app.services.movements_import import importar_movimentos, parse_datajud_movimentos
    resultado = await importar_movimentos(
        db, process, parse_datajud_movimentos(dados, limite=200), notificar=True,
    )
    novos = resultado["novos"]
    await db.commit()
    return {
        "novos": novos,
        "fonte_respondeu": True,
        "message": (f"{novos} novo(s) andamento(s) importado(s)." if novos
                    else "Nenhum andamento novo — o processo já está atualizado."),
    }


@router.post("/{process_id}/atualizar-partes")
async def atualizar_partes(
    process_id: str,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "ADVOGADO", "GESTOR", "PARALEGAL", "ASSISTENTE")),
    db: AsyncSession = Depends(get_db),
):
    """Backfill das PARTES do processo via PDPJ (fonte credenciada, Fase 75).

    Exige que o escritório tenha conectado o provedor "pdpj" em Integrações
    (opt-in). Sem credencial → 422 orientando a conectar. O DataJud público não
    expõe partes, por isso este caminho é separado."""
    from fastapi import HTTPException
    from app.integrations.fontes.credenciadas import fonte_partes_credenciada
    from app.services.partes_import import importar_partes

    process = (await db.execute(
        select(LegalProcess).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if not process:
        raise NotFoundError("Processo", process_id)
    if not process.numero_cnj:
        raise HTTPException(status_code=422, detail="Processo sem número CNJ — não é possível consultar a fonte de partes.")

    fonte = await fonte_partes_credenciada(db, current_user.tenant_id)
    if not fonte:
        raise HTTPException(
            status_code=422,
            detail="Nenhuma fonte de partes conectada. Conecte PJe/PDPJ, Escavador, Judit ou Jusbrasil em Integrações.",
        )

    try:
        partes = await fonte.partes(process.numero_cnj, process.tribunal)
    except Exception:
        partes = []
    if not partes:
        return {"novas": 0, "fonte_respondeu": False,
                "message": f"{fonte.nome.upper()} não retornou partes (token expirado/sem acesso ao processo, ou fora do ar)."}

    resultado = await importar_partes(db, process, partes, origem=fonte.nome.upper())
    await db.commit()
    novas = resultado["novas"]
    return {
        "novas": novas,
        "total": resultado["total"],
        "fonte_respondeu": True,
        "message": (f"{novas} nova(s) parte(s) importada(s)." if novas
                    else "Nenhuma parte nova — as partes já estão atualizadas."),
    }


# ─── Reatribuição de carteira (advogado sai / entra de férias) ───────────────
class ReatribuirCarteira(BaseModel):
    de_advogado_id: str
    para_advogado_id: str
    incluir_colaboracoes: bool = True   # também transfere onde é COLABORADOR
    apenas_ativos: bool = True          # só processos ATIVO/SUSPENSO


async def _transferir_participacao(db: AsyncSession, process_id: uuid.UUID,
                                   de: uuid.UUID, para: uuid.UUID, papel: str) -> None:
    """Move a participação de `de` para `para` num processo, respeitando o unique
    (process_id, user_id): se `para` já participa, remove a linha de `de` e apenas
    promove `para` a RESPONSAVEL quando for o caso."""
    rows = (await db.execute(
        select(ProcessTeamMember).where(
            ProcessTeamMember.process_id == process_id,
            ProcessTeamMember.user_id.in_([de, para]),
        )
    )).scalars().all()
    de_row = next((r for r in rows if r.user_id == de), None)
    para_row = next((r for r in rows if r.user_id == para), None)
    if de_row is not None:
        await db.delete(de_row)
    if para_row is not None:
        if papel == "RESPONSAVEL":
            para_row.papel = "RESPONSAVEL"
    else:
        db.add(ProcessTeamMember(process_id=process_id, user_id=para, papel=papel))


@router.get("/carteira/{user_id}")
async def get_carteira(
    user_id: str,
    # Ver a carteira de um advogado é ação de gestão
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    """Resumo da carteira de um advogado (para prévia antes de reatribuir)."""
    from sqlalchemy import func
    uid = uuid.UUID(user_id)
    await _validar_advogados_do_tenant(db, current_user.tenant_id, [uid])

    como_resp = (await db.execute(
        select(func.count(LegalProcess.id)).where(
            LegalProcess.tenant_id == current_user.tenant_id,
            LegalProcess.responsavel_id == uid,
        )
    )).scalar_one() or 0
    resp_ativos = (await db.execute(
        select(func.count(LegalProcess.id)).where(
            LegalProcess.tenant_id == current_user.tenant_id,
            LegalProcess.responsavel_id == uid,
            LegalProcess.situacao.in_(["ATIVO", "SUSPENSO"]),
        )
    )).scalar_one() or 0
    como_colab = (await db.execute(
        select(func.count(ProcessTeamMember.id))
        .join(LegalProcess, LegalProcess.id == ProcessTeamMember.process_id)
        .where(
            LegalProcess.tenant_id == current_user.tenant_id,
            ProcessTeamMember.user_id == uid,
            ProcessTeamMember.papel == "COLABORADOR",
        )
    )).scalar_one() or 0
    prazos_pendentes = (await db.execute(
        select(func.count(ProcessDeadline.id))
        .join(LegalProcess, LegalProcess.id == ProcessDeadline.process_id)
        .where(
            LegalProcess.tenant_id == current_user.tenant_id,
            ProcessDeadline.responsavel_id == uid,
            ProcessDeadline.status == "PENDENTE",
        )
    )).scalar_one() or 0
    return {
        "responsavel": int(como_resp),
        "responsavel_ativos": int(resp_ativos),
        "colaborador": int(como_colab),
        "prazos_pendentes": int(prazos_pendentes),
    }


@router.post("/reatribuir")
async def reatribuir_carteira(
    body: ReatribuirCarteira,
    # Reatribuir a carteira de outro advogado é ação de gestão
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    """Transfere a carteira de um advogado para outro: processos onde é responsável
    (e, opcionalmente, onde é colaborador) + os prazos pendentes correspondentes.
    Usado quando um advogado deixa o escritório ou entra de licença."""
    from fastapi import HTTPException
    from sqlalchemy import update as sa_update
    from app.models.notification import Notification

    de = uuid.UUID(body.de_advogado_id)
    para = uuid.UUID(body.para_advogado_id)
    if de == para:
        raise HTTPException(status_code=422, detail="Selecione advogados diferentes.")
    nomes = await _validar_advogados_do_tenant(db, current_user.tenant_id, [de, para])

    # 1. Processos onde `de` é o responsável
    q = select(LegalProcess).where(
        LegalProcess.tenant_id == current_user.tenant_id,
        LegalProcess.responsavel_id == de,
    )
    if body.apenas_ativos:
        q = q.where(LegalProcess.situacao.in_(["ATIVO", "SUSPENSO"]))
    processos_resp = (await db.execute(q)).scalars().all()
    afetados: set[uuid.UUID] = set()
    for p in processos_resp:
        p.responsavel_id = para
        await _transferir_participacao(db, p.id, de, para, "RESPONSAVEL")
        afetados.add(p.id)

    # Prazos pendentes desses processos: seguem o novo responsável
    if afetados:
        await db.execute(
            sa_update(ProcessDeadline)
            .where(
                ProcessDeadline.process_id.in_(afetados),
                ProcessDeadline.responsavel_id == de,
                ProcessDeadline.status == "PENDENTE",
            )
            .values(responsavel_id=para)
        )

    # 2. Participações como colaborador (opcional)
    colaboracoes = 0
    if body.incluir_colaboracoes:
        rows = (await db.execute(
            select(ProcessTeamMember.process_id)
            .join(LegalProcess, LegalProcess.id == ProcessTeamMember.process_id)
            .where(
                LegalProcess.tenant_id == current_user.tenant_id,
                ProcessTeamMember.user_id == de,
                ProcessTeamMember.papel == "COLABORADOR",
            )
        )).all()
        for (pid,) in rows:
            await _transferir_participacao(db, pid, de, para, "COLABORADOR")
            colaboracoes += 1
            afetados.add(pid)

    # 3. Notifica o advogado de destino
    if afetados:
        from app.services.notification import publish_notification_ws
        notif = Notification(
            user_id=para,
            tenant_id=current_user.tenant_id,
            tipo="NOVO_ANDAMENTO",
            titulo="Carteira reatribuída a você",
            corpo=(f"{len(processos_resp)} processo(s) como responsável"
                   + (f" e {colaboracoes} como colaborador" if colaboracoes else "")
                   + f" foram transferidos de {nomes.get(de, 'outro advogado')}."),
            priority="HIGH",
            link="/minha-area",
        )
        db.add(notif)
        await publish_notification_ws(notif)

    await db.commit()
    return {
        "de": nomes.get(de),
        "para": nomes.get(para),
        "processos_responsavel": len(processos_resp),
        "colaboracoes": colaboracoes,
        "processos_afetados": len(afetados),
    }


@router.delete("/{process_id}", status_code=204)
async def archive_process(
    process_id: str,
    desfecho: str | None = Query(default=None),  # EXITO/PARCIAL/ACORDO/DERROTA (taxa de êxito)
    # Arquivar tira o processo da operação — restrito a advogados e gestão
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "ADVOGADO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LegalProcess).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    process = result.scalar_one_or_none()
    if not process:
        raise NotFoundError("Processo", process_id)
    process.situacao = "ARQUIVADO"
    process.monitoring_active = False
    if desfecho in ("EXITO", "PARCIAL", "ACORDO", "DERROTA"):
        process.desfecho = desfecho
    await db.flush()


class MovementCreate(BaseModel):
    descricao: str
    tipo: str | None = None
    data_movimento: str | None = None


@router.post("/{process_id}/movements", status_code=201)
async def create_movement(
    process_id: str,
    body: MovementCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
    result = await db.execute(
        select(LegalProcess).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    if not result.scalar_one_or_none():
        raise NotFoundError("Processo", process_id)
    try:
        data_mov = datetime.fromisoformat(body.data_movimento) if body.data_movimento else datetime.now(timezone.utc)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Formato de data inválido. Use ISO 8601: YYYY-MM-DDTHH:MM:SS")
    movement = ProcessMovement(
        process_id=uuid.UUID(process_id),
        descricao=body.descricao,
        tipo=body.tipo,
        data_movimento=data_mov,
    )
    db.add(movement)
    await db.flush()
    return {
        "id": str(movement.id),
        "process_id": process_id,
        "descricao": movement.descricao,
        "tipo": movement.tipo,
        "data_movimento": movement.data_movimento.isoformat(),
    }


async def _tenant_feriados(db: AsyncSession, tenant_id) -> list[str]:
    """Feriados forenses locais do escritório (TenantConfig.extra_data)."""
    from app.models.tenant import TenantConfig
    if not tenant_id:
        return []
    cfg = (await db.execute(
        select(TenantConfig).where(TenantConfig.tenant_id == tenant_id)
    )).scalar_one_or_none()
    fer = (cfg.extra_data or {}).get("feriados_forenses", []) if cfg else []
    if not isinstance(fer, list):
        return []
    # Aceita itens no formato {"data": "YYYY-MM-DD", ...} ou string ISO (retrocompat).
    datas = []
    for f in fer:
        if isinstance(f, dict) and f.get("data"):
            datas.append(str(f["data"])[:10])
        elif isinstance(f, str):
            datas.append(f[:10])
    return datas


class PrazoCalcRequest(BaseModel):
    data_intimacao: str
    dias: int
    dias_uteis: bool = True


@router.post("/deadlines/calcular")
async def calcular_prazo_preview(
    body: PrazoCalcRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Prévia do cálculo de prazo (não salva) — dias úteis + feriados forenses."""
    from datetime import date as date_type
    from app.utils.prazo import calcular_prazo
    try:
        r = calcular_prazo(
            date_type.fromisoformat(body.data_intimacao),
            body.dias,
            body.dias_uteis,
            await _tenant_feriados(db, current_user.tenant_id),
        )
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "termo_inicial": r["termo_inicial"].isoformat(),
        "data_prazo": r["data_prazo"].isoformat(),
        "feriados_no_periodo": r["feriados_no_periodo"],
        "dias": r["dias"],
        "dias_uteis": r["dias_uteis"],
    }


class DeadlineCreate(BaseModel):
    descricao: str
    tipo: str | None = None
    data_prazo: str | None = None          # opcional se calcular por intimação
    data_fatal: str | None = None
    observacoes: str | None = None
    # Cálculo automático (opcional): se data_prazo não vier, deriva de intimação.
    data_intimacao: str | None = None
    dias: int | None = None
    dias_uteis: bool = True


@router.post("/{process_id}/deadlines", status_code=201)
async def create_deadline(
    process_id: str,
    body: DeadlineCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date as date_type
    from fastapi import HTTPException
    result = await db.execute(
        select(LegalProcess).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    if not result.scalar_one_or_none():
        raise NotFoundError("Processo", process_id)

    # Fonte da verdade: se veio data_prazo, usa; senão calcula por intimação+dias.
    if body.data_prazo:
        data_prazo = date_type.fromisoformat(body.data_prazo)
        data_fatal = date_type.fromisoformat(body.data_fatal) if body.data_fatal else None
    elif body.data_intimacao and body.dias:
        from app.utils.prazo import calcular_prazo
        try:
            r = calcular_prazo(
                date_type.fromisoformat(body.data_intimacao),
                body.dias,
                body.dias_uteis,
                await _tenant_feriados(db, current_user.tenant_id),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        data_prazo = r["data_prazo"]
        data_fatal = r["data_prazo"]
    else:
        raise HTTPException(status_code=422, detail="Informe data_prazo ou (data_intimacao + dias).")

    deadline = ProcessDeadline(
        process_id=uuid.UUID(process_id),
        descricao=body.descricao,
        tipo=body.tipo,
        data_prazo=data_prazo,
        data_fatal=data_fatal,
        status="PENDENTE",
        responsavel_id=current_user.id,
    )
    db.add(deadline)
    await db.flush()

    from app.services.deadline_calendar import sincronizar_prazo_no_google
    await sincronizar_prazo_no_google(db, deadline, current_user.id)

    return {
        "id": str(deadline.id),
        "process_id": process_id,
        "descricao": deadline.descricao,
        "tipo": deadline.tipo,
        "data_prazo": deadline.data_prazo.isoformat(),
        "data_fatal": deadline.data_fatal.isoformat() if deadline.data_fatal else None,
        "status": deadline.status,
    }


class DeadlineUpdate(BaseModel):
    status: str
    descricao: str | None = None


@router.put("/{process_id}/deadlines/{deadline_id}")
async def update_deadline(
    process_id: str,
    deadline_id: str,
    body: DeadlineUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Garante que o processo pertence ao tenant do usuário antes de tocar no prazo
    proc_check = await db.execute(
        select(LegalProcess.id).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    if not proc_check.scalar_one_or_none():
        raise NotFoundError("Processo", process_id)

    result = await db.execute(
        select(ProcessDeadline).where(
            ProcessDeadline.id == uuid.UUID(deadline_id),
            ProcessDeadline.process_id == uuid.UUID(process_id),
        )
    )
    deadline = result.scalar_one_or_none()
    if not deadline:
        raise NotFoundError("Prazo", deadline_id)
    deadline.status = body.status
    if body.descricao:
        deadline.descricao = body.descricao
    await db.flush()
    return {"id": str(deadline.id), "status": deadline.status}


def _to_response(p: LegalProcess) -> ProcessResponse:
    return ProcessResponse(
        id=str(p.id),
        numero_cnj=p.numero_cnj,
        tribunal=p.tribunal,
        vara=p.vara,
        comarca=p.comarca,
        uf=p.uf,
        tipo_acao=p.tipo_acao,
        area_direito=p.area_direito,
        fase=p.fase,
        situacao=p.situacao,
        desfecho=p.desfecho,
        valor_causa=float(p.valor_causa) if p.valor_causa else None,
        client_id=str(p.client_id) if p.client_id else None,
        parte_contraria=p.parte_contraria,
        polo=p.polo,
        oab_responsavel=p.oab_responsavel,
        descricao=p.descricao,
        responsavel_id=str(p.responsavel_id) if p.responsavel_id else None,
        proximo_prazo_at=p.proximo_prazo_at.isoformat() if p.proximo_prazo_at else None,
        ultimo_andamento_at=p.ultimo_andamento_at.isoformat() if p.ultimo_andamento_at else None,
        monitoring_active=p.monitoring_active,
        fonte=p.fonte,
        created_at=p.created_at.isoformat(),
    )
