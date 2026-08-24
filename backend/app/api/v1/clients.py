"""Endpoints CRUD de clientes / CRM."""
from fastapi import APIRouter, Depends, Query, Response, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_, func
from pydantic import BaseModel
from typing import Any
import re
import uuid
from datetime import date, datetime, timezone
import structlog

from app.db.base import get_db
from app.dependencies import get_current_user, require_role
from app.models.user import User
from app.models.client import Client, ClientContact, ClientInteraction
from app.core.exceptions import NotFoundError
from app.core.crypto import encrypt, decrypt_or_raw
from app.models.gov_registry_lookup import GovRegistryLookup
from app.integrations.serpro.consulta_cpf_cnpj import consultar_cpf, consultar_cnpj
from app.integrations.publicas.cep_lookup import consultar_cep as _consultar_cep_externa

log = structlog.get_logger()
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
    endereco_json: dict[str, Any] | None = None  # {cep, logradouro, bairro, cidade, uf}
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
    cpf: str | None = None
    cnpj: str | None = None
    endereco_json: dict[str, Any] | None = None
    observacoes: str | None = None
    status: str
    segmento: str | None = None
    origem: str | None
    lgpd_consent: bool
    created_at: str


class ContactCreate(BaseModel):
    nome: str
    cargo: str | None = None
    email: str | None = None
    telefone: str | None = None
    whatsapp: str | None = None  # stored in telefone if no dedicated column
    is_primary: bool = False


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
    query = (
        select(Client)
        .where(Client.tenant_id == current_user.tenant_id)
        .order_by(desc(Client.created_at))
        .offset(offset)
        .limit(limit)
    )
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


async def _geocodificar_endereco(endereco: dict | None) -> dict | None:
    """Fase 230 — preenche latitude/longitude no endereço via BrasilAPI
    (mesma fonte de `POST /clients/consultar-cep`, Fase 217) quando o
    endereço tem CEP mas ainda não tem coordenadas — groundwork pro mapa
    com marcadores de cliente/escritório planejado pra uma fase futura.
    Fail-soft: nunca lança, nunca bloqueia o save do cliente/escritório se
    a geocodificação falhar/estiver indisponível; precisão de CEP, não do
    número exato do endereço (limitação da própria BrasilAPI)."""
    if not endereco or not endereco.get("cep"):
        return endereco
    if endereco.get("latitude") is not None and endereco.get("longitude") is not None:
        return endereco
    resultado = await _consultar_cep_externa(endereco["cep"])
    if resultado and resultado.get("latitude") is not None:
        endereco = {**endereco, "latitude": resultado["latitude"], "longitude": resultado["longitude"]}
    return endereco


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
    data["tenant_id"] = current_user.tenant_id
    if "cpf" in data:
        data["cpf"] = encrypt(data["cpf"])
    if "cnpj" in data:
        data["cnpj"] = encrypt(data["cnpj"])
    if "endereco_json" in data:
        data["endereco_json"] = await _geocodificar_endereco(data["endereco_json"])

    client = Client(**data)
    db.add(client)
    await db.flush()
    return _to_response(client)


@router.get("/match")
async def match_client(
    cpf_cnpj: str | None = None,
    nome: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fase 181 — vínculo automático de cliente ao cadastrar parte de processo.

    `Client.cpf`/`cnpj` são cifrados (Fase 149, Fernet — IV aleatório a cada
    encrypt()), então não dá pra comparar via WHERE no banco: decifra as
    linhas do tenant e compara os dígitos normalizados em Python, mesmo
    caminho que `_to_response`/exportação LGPD já usam."""
    import re

    match = None
    cpf_cnpj_norm = re.sub(r"\D", "", cpf_cnpj) if cpf_cnpj else ""
    if len(cpf_cnpj_norm) >= 11:
        rows = (await db.execute(
            select(Client.id, Client.nome_completo, Client.cpf, Client.cnpj).where(
                Client.tenant_id == current_user.tenant_id,
                or_(Client.cpf.isnot(None), Client.cnpj.isnot(None)),
            )
        )).all()
        for cid, nome_completo, cpf_enc, cnpj_enc in rows:
            cpf_dec = re.sub(r"\D", "", decrypt_or_raw(cpf_enc) or "")
            cnpj_dec = re.sub(r"\D", "", decrypt_or_raw(cnpj_enc) or "")
            if cpf_cnpj_norm in (cpf_dec, cnpj_dec) and (cpf_dec or cnpj_dec):
                match = {"id": str(cid), "nome_completo": nome_completo}
                break

    sugestoes = []
    nome_busca = (nome or "").strip()
    if len(nome_busca) >= 3:
        query = (
            select(Client.id, Client.nome_completo)
            .where(
                Client.tenant_id == current_user.tenant_id,
                Client.nome_completo.ilike(f"%{nome_busca}%"),
            )
            .limit(5)
        )
        if match:
            query = query.where(Client.id != uuid.UUID(match["id"]))
        rows = (await db.execute(query)).all()
        sugestoes = [{"id": str(cid), "nome_completo": nome_completo} for cid, nome_completo in rows]

    return {"match": match, "sugestoes": sugestoes}


class ValidarDocumentoBody(BaseModel):
    tipo: str  # "cpf" ou "cnpj"
    valor: str


@router.post("/validar-documento")
async def validar_documento(
    body: ValidarDocumentoBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fase 217 — valida/enriquece CPF ou CNPJ contra a Loja SERPRO no
    momento do cadastro (blur do campo no frontend). `Client.cpf`/`cnpj`
    nunca tiveram nenhuma validação de formato ou existência até aqui.

    `valido: None` (não `False`) sempre que a consulta externa não pôde ser
    feita (não configurado, indisponível, circuito aberto) — `False` é
    reservado pro caso em que a SERPRO respondeu e o documento é
    inválido/irregular. Sempre HTTP 200: indisponibilidade externa nunca
    pode bloquear o cadastro de um cliente."""
    tipo = (body.tipo or "").strip().lower()
    if tipo not in ("cpf", "cnpj"):
        raise HTTPException(status_code=422, detail="tipo deve ser 'cpf' ou 'cnpj'")

    # Fase 220 (achado da Fase 219) — normaliza e valida o formato ANTES de
    # bater SERPRO ou gravar qualquer coisa. Antes disso, `body.valor` bruto
    # (podendo ter centenas de caracteres colados no campo) era cifrado e
    # gravado direto em `documento_consultado` (String(255)) sem checagem de
    # tamanho — 500 garantido em input longo. Também elimina o resto de
    # formatação (pontos/traço) do que fica auditado.
    numero = re.sub(r"\D", "", body.valor or "")
    tamanho_esperado = 11 if tipo == "cpf" else 14
    if len(numero) != tamanho_esperado:
        return {
            "valido": False, "nome_ou_razao_social": None, "situacao_cadastral": None,
            "mensagem": "Formato de CPF/CNPJ inválido.",
        }

    resultado = await (consultar_cpf(numero) if tipo == "cpf" else consultar_cnpj(numero))

    if resultado is None:
        resposta = {
            "valido": None, "nome_ou_razao_social": None, "situacao_cadastral": None,
            "mensagem": "Validação indisponível no momento — tente novamente mais tarde.",
        }
        resumo = None
    else:
        nome = resultado.get("nome") or resultado.get("razao_social") or resultado.get("nome_empresarial")
        situacao = (resultado.get("situacao") or {}).get("nome") if isinstance(resultado.get("situacao"), dict) else resultado.get("situacao_cadastral")
        resposta = {"valido": True, "nome_ou_razao_social": nome, "situacao_cadastral": situacao, "mensagem": None}
        resumo = f"{nome or ''} — {situacao or ''}".strip(" —")

    # Fase 220 — `encrypt()` cifra o número já normalizado (11-14 dígitos,
    # nunca mais estoura a coluna). Se a criptografia falhar de verdade
    # (chave ausente/inválida), pula a gravação da auditoria em vez de cair
    # pra texto puro — único call site do código que fazia isso antes.
    documento_cifrado = encrypt(numero)
    if documento_cifrado:
        db.add(GovRegistryLookup(
            tenant_id=current_user.tenant_id,
            tipo_consulta=tipo.upper(),
            documento_consultado=documento_cifrado,
            resultado_resumo=resumo,
            consultado_por=current_user.id,
        ))
        await db.commit()
    else:
        log.error("gov_registry_lookup_encrypt_falhou", tipo=tipo)

    return resposta


class ConsultarCepBody(BaseModel):
    cep: str


@router.post("/consultar-cep")
async def consultar_cep_endpoint(
    body: ConsultarCepBody,
    current_user: User = Depends(get_current_user),
):
    """Fase 217 — autofill de endereço a partir do CEP, via BrasilAPI
    (pública, gratuita, terceiro — não é canal oficial de governo, ver
    docstring de `integrations/publicas/cep_lookup.py`). Sem gravação de
    auditoria — não é consulta de identidade pessoal."""
    resultado = await _consultar_cep_externa(body.cep)
    if resultado is None:
        return {"logradouro": None, "bairro": None, "cidade": None, "uf": None, "latitude": None, "longitude": None}
    return resultado


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Client).where(
            Client.id == uuid.UUID(client_id),
            Client.tenant_id == current_user.tenant_id,
        )
    )
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
    result = await db.execute(
        select(Client).where(
            Client.id == uuid.UUID(client_id),
            Client.tenant_id == current_user.tenant_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise NotFoundError("Cliente", client_id)

    for field, value in body.model_dump(exclude_none=True).items():
        if field in ("cpf", "cnpj"):
            value = encrypt(value)
        elif field == "endereco_json":
            value = await _geocodificar_endereco(value)
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
    result = await db.execute(
        select(Client).where(
            Client.id == uuid.UUID(client_id),
            Client.tenant_id == current_user.tenant_id,
        )
    )
    if not result.scalar_one_or_none():
        raise NotFoundError("Cliente", client_id)

    # Interações tipo PORTAL aparecem no portal do cliente como resposta do escritório
    metadata = dict(body.metadata_json or {})
    if body.tipo == "PORTAL":
        metadata.setdefault("origem", "escritorio")

    interaction = ClientInteraction(
        client_id=uuid.UUID(client_id),
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        tipo=body.tipo,
        descricao=body.descricao,
        metadata_json=metadata or None,
    )
    db.add(interaction)
    await db.flush()
    return {"message": "Interação registrada", "client_id": client_id}


@router.get("/{client_id}/interactions")
async def get_interactions(
    client_id: str,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client_check = await db.execute(
        select(Client.id).where(
            Client.id == uuid.UUID(client_id),
            Client.tenant_id == current_user.tenant_id,
        )
    )
    if not client_check.scalar_one_or_none():
        raise NotFoundError("Cliente", client_id)
    result = await db.execute(
        select(ClientInteraction)
        .where(
            ClientInteraction.client_id == uuid.UUID(client_id),
            # Fase 153 — tenant_id é NULL em linhas anteriores à migração
            # (sem backfill, mesmo padrão de toda a sessão); client_id já
            # foi validado contra o tenant acima, então o filtro aqui é
            # defesa em profundidade, não a única barreira.
            or_(
                ClientInteraction.tenant_id == current_user.tenant_id,
                ClientInteraction.tenant_id.is_(None),
            ),
        )
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


@router.get("/{client_id}/contacts")
async def list_contacts(
    client_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Client).where(
            Client.id == uuid.UUID(client_id),
            Client.tenant_id == current_user.tenant_id,
        )
    )
    if not result.scalar_one_or_none():
        raise NotFoundError("Cliente", client_id)

    contacts_result = await db.execute(
        select(ClientContact)
        .where(ClientContact.client_id == uuid.UUID(client_id))
        .order_by(ClientContact.is_primary.desc())
    )
    contacts = contacts_result.scalars().all()
    return [_contact_to_dict(c) for c in contacts]


@router.post("/{client_id}/contacts", status_code=201)
async def create_contact(
    client_id: str,
    body: ContactCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Client).where(
            Client.id == uuid.UUID(client_id),
            Client.tenant_id == current_user.tenant_id,
        )
    )
    if not result.scalar_one_or_none():
        raise NotFoundError("Cliente", client_id)

    contact = ClientContact(
        client_id=uuid.UUID(client_id),
        nome=body.nome,
        cargo=body.cargo,
        email=body.email,
        telefone=body.telefone or body.whatsapp,
        is_primary=body.is_primary,
    )
    db.add(contact)
    await db.flush()
    return _contact_to_dict(contact)


@router.put("/{client_id}/contacts/{contact_id}")
async def update_contact(
    client_id: str,
    contact_id: str,
    body: ContactCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Client).where(
            Client.id == uuid.UUID(client_id),
            Client.tenant_id == current_user.tenant_id,
        )
    )
    if not result.scalar_one_or_none():
        raise NotFoundError("Cliente", client_id)

    contact_result = await db.execute(
        select(ClientContact).where(
            ClientContact.id == uuid.UUID(contact_id),
            ClientContact.client_id == uuid.UUID(client_id),
        )
    )
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise NotFoundError("Contato", contact_id)

    contact.nome = body.nome
    contact.cargo = body.cargo
    contact.email = body.email
    contact.telefone = body.telefone or body.whatsapp
    contact.is_primary = body.is_primary
    return _contact_to_dict(contact)


@router.delete("/{client_id}/contacts/{contact_id}", status_code=204)
async def delete_contact(
    client_id: str,
    contact_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Client).where(
            Client.id == uuid.UUID(client_id),
            Client.tenant_id == current_user.tenant_id,
        )
    )
    if not result.scalar_one_or_none():
        raise NotFoundError("Cliente", client_id)

    contact_result = await db.execute(
        select(ClientContact).where(
            ClientContact.id == uuid.UUID(contact_id),
            ClientContact.client_id == uuid.UUID(client_id),
        )
    )
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise NotFoundError("Contato", contact_id)

    await db.delete(contact)


@router.delete("/{client_id}", status_code=204)
async def delete_client(
    client_id: str,
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Client).where(
            Client.id == uuid.UUID(client_id),
            Client.tenant_id == current_user.tenant_id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise NotFoundError("Cliente", client_id)
    client.status = "INATIVO"
    client.cpf = None
    client.cnpj = None
    client.email = f"[removido]@{client_id[:8]}.invalid"
    client.telefone = None
    client.whatsapp = None
    await db.flush()


# LGPD (portabilidade e direito ao esquecimento) vive em app/api/v1/lgpd.py
# (/lgpd/clients/{id}/export e /lgpd/clients/{id}/data) — o frontend usa aquelas
# rotas. As duplicatas que existiam aqui foram removidas para não manter dois
# caminhos divergentes de uma operação sensível de dados. (Fase 48)


def _contact_to_dict(c: ClientContact) -> dict:
    return {
        "id": str(c.id),
        "nome": c.nome,
        "cargo": c.cargo,
        "email": c.email,
        "telefone": c.telefone,
        "whatsapp": c.whatsapp,
        "is_primary": c.is_primary,
    }


def _to_response(c: Client) -> ClientResponse:
    return ClientResponse(
        id=str(c.id),
        tipo=c.tipo,
        nome_completo=c.nome_completo,
        razao_social=c.razao_social,
        email=c.email,
        telefone=c.telefone,
        whatsapp=c.whatsapp,
        cpf=decrypt_or_raw(c.cpf),
        cnpj=decrypt_or_raw(c.cnpj),
        endereco_json=c.endereco_json,
        observacoes=c.observacoes,
        status=c.status,
        segmento=c.segmento,
        origem=c.origem,
        lgpd_consent=c.lgpd_consent,
        created_at=c.created_at.isoformat(),
    )


@router.get("/{client_id}/financeiro")
async def client_financeiro(
    client_id: str,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    """Visão financeira 360° do cliente: resumo, lançamentos e faturas."""
    from app.models.financial import FinancialEntry, BillingInvoice

    cliente = (await db.execute(
        select(Client).where(Client.id == uuid.UUID(client_id), Client.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()
    if not cliente:
        raise NotFoundError("Cliente", client_id)

    # Resumo por tipo/status (tenant-scoped implícito pelo cliente do tenant)
    rows = (await db.execute(
        select(FinancialEntry.tipo, FinancialEntry.status, func.coalesce(func.sum(FinancialEntry.valor), 0))
        .where(FinancialEntry.client_id == cliente.id, FinancialEntry.tenant_id == current_user.tenant_id)
        .group_by(FinancialEntry.tipo, FinancialEntry.status)
    )).all()
    agg = {(t, s): float(v or 0) for t, s, v in rows}
    receita_paga = agg.get(("RECEITA", "PAGO"), 0.0)
    receita_pendente = agg.get(("RECEITA", "PENDENTE"), 0.0)
    despesa = sum(v for (t, s), v in agg.items() if t == "DESPESA")

    lancamentos = (await db.execute(
        select(FinancialEntry)
        .where(FinancialEntry.client_id == cliente.id, FinancialEntry.tenant_id == current_user.tenant_id)
        .order_by(desc(FinancialEntry.created_at)).limit(50)
    )).scalars().all()

    faturas = (await db.execute(
        select(BillingInvoice)
        .where(BillingInvoice.client_id == cliente.id, BillingInvoice.tenant_id == current_user.tenant_id)
        .order_by(desc(BillingInvoice.created_at)).limit(50)
    )).scalars().all()

    return {
        "resumo": {
            "receita_paga": receita_paga,
            "receita_pendente": receita_pendente,
            "despesa": despesa,
            "saldo": receita_paga - despesa,
        },
        "lancamentos": [
            {
                "id": str(e.id), "tipo": e.tipo, "categoria": e.categoria, "descricao": e.descricao,
                "valor": float(e.valor), "status": e.status,
                "data_vencimento": e.data_vencimento.isoformat() if e.data_vencimento else None,
            } for e in lancamentos
        ],
        "faturas": [
            {
                "id": str(f.id), "numero": f.numero, "valor_total": float(f.valor_total or 0),
                "status": f.status,
                "data_vencimento": f.data_vencimento.isoformat() if f.data_vencimento else None,
            } for f in faturas
        ],
    }


@router.get("/{client_id}/health-score")
async def client_health_score(
    client_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fase 207.1 — score de saúde do cliente (0-100), combinando 3 sinais já
    existentes: confiabilidade de pagamento (40 pts), engajamento recente via
    interações (30 pts) e taxa de êxito dos processos (30 pts). Puramente
    informativo — não aciona nenhuma ação automática, não bloqueia nada."""
    from app.models.financial import FinancialEntry
    from app.models.process import LegalProcess, client_linked_processes_filter

    cliente = (await db.execute(
        select(Client).where(Client.id == uuid.UUID(client_id), Client.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()
    if not cliente:
        raise NotFoundError("Cliente", client_id)

    hoje = date.today()

    # ── Financeiro (40 pts) — penaliza só receita PENDENTE já vencida. Sem
    # nenhum lançamento de receita ainda, não há sinal negativo: pontuação cheia.
    receitas = (await db.execute(
        select(FinancialEntry.status, FinancialEntry.data_vencimento)
        .where(FinancialEntry.client_id == cliente.id, FinancialEntry.tenant_id == current_user.tenant_id,
               FinancialEntry.tipo == "RECEITA")
    )).all()
    total_receita = len(receitas)
    atrasadas = sum(1 for status, venc in receitas if status == "PENDENTE" and venc and venc < hoje)
    score_financeiro = 40 if not total_receita else round(40 * max(0.0, 1 - atrasadas / total_receita))

    # ── Engajamento (30 pts) — recência da última interação registrada.
    ultima_interacao = (await db.execute(
        select(func.max(ClientInteraction.created_at))
        .where(ClientInteraction.client_id == cliente.id, ClientInteraction.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()
    dias_desde_interacao = None
    if ultima_interacao is None:
        score_engajamento = 15  # sem histórico ainda — neutro, não penaliza
    else:
        dias_desde_interacao = (datetime.now(timezone.utc) - ultima_interacao).days
        if dias_desde_interacao <= 30:
            score_engajamento = 30
        elif dias_desde_interacao <= 90:
            score_engajamento = 18
        else:
            score_engajamento = 8

    # ── Processual (30 pts) — taxa de êxito entre os processos já encerrados.
    # Processos em andamento (sem desfecho) não penalizam nem beneficiam.
    desf_rows = (await db.execute(
        select(LegalProcess.desfecho, func.count(LegalProcess.id))
        .where(client_linked_processes_filter(cliente.id), LegalProcess.tenant_id == current_user.tenant_id,
               LegalProcess.desfecho.is_not(None))
        .group_by(LegalProcess.desfecho)
    )).all()
    total_desfecho = sum(n for _, n in desf_rows)
    ganhos = sum(n for d, n in desf_rows if d in ("EXITO", "ACORDO"))
    score_processual = 30 if not total_desfecho else round(30 * ganhos / total_desfecho)

    score = score_financeiro + score_engajamento + score_processual
    banda = "saudavel" if score >= 75 else "atencao" if score >= 50 else "risco"

    return {
        "score": score,
        "banda": banda,
        "componentes": {
            "financeiro": {
                "pontos": score_financeiro, "max": 40,
                "receita_atrasada": atrasadas, "receita_total": total_receita,
            },
            "engajamento": {
                "pontos": score_engajamento, "max": 30,
                "dias_desde_ultima_interacao": dias_desde_interacao,
            },
            "processual": {
                "pontos": score_processual, "max": 30,
                "taxa_exito": round(100 * ganhos / total_desfecho, 1) if total_desfecho else None,
                "total_com_desfecho": total_desfecho,
            },
        },
    }


@router.get("/{client_id}/timeline")
async def client_timeline(
    client_id: str,
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fase 211 (proposta de evolução da Fase 209) — timeline unificada do
    Cliente 360: junta interações, marcos processuais (abertura/desfecho),
    pagamentos recebidos e petições protocoladas numa única lista
    cronológica, pra evitar que o advogado precise navegar entre 4 telas
    separadas pra reconstruir "o que aconteceu com esse cliente".
    Puramente read-only, agregando dado que já existe — nenhum campo novo."""
    from app.models.document import Document
    from app.models.financial import FinancialEntry
    from app.models.process import LegalProcess, client_linked_processes_filter

    cliente = (await db.execute(
        select(Client).where(Client.id == uuid.UUID(client_id), Client.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()
    if not cliente:
        raise NotFoundError("Cliente", client_id)

    eventos: list[dict] = []

    interacoes = (await db.execute(
        select(ClientInteraction).where(
            ClientInteraction.client_id == cliente.id, ClientInteraction.tenant_id == current_user.tenant_id,
        )
    )).scalars().all()
    for i in interacoes:
        eventos.append({
            "tipo": "interacao", "subtipo": i.tipo, "titulo": i.tipo,
            "detalhe": i.descricao, "data": i.created_at,
        })

    processos = (await db.execute(
        select(LegalProcess).where(
            client_linked_processes_filter(cliente.id), LegalProcess.tenant_id == current_user.tenant_id,
        )
    )).scalars().all()
    for p in processos:
        eventos.append({
            "tipo": "processo", "subtipo": "aberto", "titulo": f"Processo {p.numero_cnj} aberto",
            "detalhe": p.tribunal, "data": p.created_at,
        })
        if p.desfecho:
            # `updated_at` como proxy de "quando o desfecho foi registrado" —
            # mesma aproximação já aceita em 205.1/206.3 (o model não tem um
            # timestamp dedicado pra isso).
            eventos.append({
                "tipo": "processo", "subtipo": "desfecho", "titulo": f"Processo {p.numero_cnj} encerrado",
                "detalhe": p.desfecho, "data": p.updated_at,
            })

    pagamentos = (await db.execute(
        select(FinancialEntry).where(
            FinancialEntry.client_id == cliente.id, FinancialEntry.tenant_id == current_user.tenant_id,
            FinancialEntry.tipo == "RECEITA", FinancialEntry.status == "PAGO",
            FinancialEntry.data_pagamento.is_not(None),
        )
    )).scalars().all()
    for f in pagamentos:
        eventos.append({
            "tipo": "financeiro", "subtipo": "pagamento", "titulo": "Pagamento recebido",
            "detalhe": f.descricao, "data": datetime.combine(f.data_pagamento, datetime.min.time(), tzinfo=timezone.utc),
        })

    protocolos = (await db.execute(
        select(Document).where(
            Document.client_id == cliente.id, Document.tenant_id == current_user.tenant_id,
            Document.protocolado_em.is_not(None),
        )
    )).scalars().all()
    for d in protocolos:
        eventos.append({
            "tipo": "documento", "subtipo": "protocolado", "titulo": f'"{d.titulo}" protocolada',
            "detalhe": None, "data": d.protocolado_em,
        })

    eventos.sort(key=lambda e: e["data"], reverse=True)
    return eventos[:limit]


@router.get("/{client_id}/dossie-pdf")
async def client_dossie_pdf(
    client_id: str,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    """Fase 214 (proposta de evolução da Fase 209) — dossiê do cliente em
    PDF, reunindo dados básicos, score de saúde (207.1), processos e
    linha do tempo (211) num único documento pra levar a uma reunião ou
    consultar formatado. Reaproveita `client_health_score`/`client_timeline`
    diretamente (mesma fonte de verdade da Cliente 360) em vez de duplicar
    a lógica de agregação. Mesmo gate de `/financeiro` — o dossiê inclui
    dado financeiro (via health-score)."""
    from app.models.process import LegalProcess, client_linked_processes_filter
    from app.utils.pdf_builder import build_report_pdf

    cliente = (await db.execute(
        select(Client).where(Client.id == uuid.UUID(client_id), Client.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()
    if not cliente:
        raise NotFoundError("Cliente", client_id)

    health = await client_health_score(client_id, current_user, db)
    timeline = await client_timeline(client_id, 20, current_user, db)
    processos = (await db.execute(
        select(LegalProcess).where(client_linked_processes_filter(cliente.id), LegalProcess.tenant_id == current_user.tenant_id)
    )).scalars().all()

    dados_cliente = "\n".join(filter(None, [
        f"Nome: {cliente.nome_completo}",
        f"Tipo: {cliente.tipo}",
        f"Status: {cliente.status}",
        f"E-mail: {cliente.email}" if cliente.email else None,
        f"Telefone: {cliente.telefone}" if cliente.telefone else None,
    ]))

    banda_label = {"saudavel": "Saudável", "atencao": "Atenção", "risco": "Risco"}.get(health["banda"], health["banda"])
    saude = (
        f"Score geral: {health['score']}/100 ({banda_label})\n"
        f"Pagamentos em dia: {health['componentes']['financeiro']['pontos']}/40\n"
        f"Engajamento recente: {health['componentes']['engajamento']['pontos']}/30\n"
        f"Taxa de êxito processual: {health['componentes']['processual']['pontos']}/30"
    )

    processos_txt = "\n".join(
        f"{p.numero_cnj or '(sem número)'} — {p.tribunal} — {p.situacao}" for p in processos
    ) or "Nenhum processo cadastrado."

    timeline_txt = "\n".join(
        f"{ev['data'][:10] if isinstance(ev['data'], str) else ev['data'].strftime('%d/%m/%Y')} — {ev['titulo']}"
        for ev in timeline
    ) or "Sem eventos registrados."

    letterhead = None
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

    pdf = build_report_pdf(
        title=f"Dossiê — {cliente.nome_completo}",
        sections=[
            {"heading": "Dados do Cliente", "body": dados_cliente},
            {"heading": "Saúde do Cliente", "body": saude},
            {"heading": "Processos", "body": processos_txt},
            {"heading": "Linha do Tempo (últimos eventos)", "body": timeline_txt},
        ],
        letterhead=letterhead,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="dossie_{client_id}.pdf"'},
    )
