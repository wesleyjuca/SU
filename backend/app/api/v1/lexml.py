"""API LexML — pesquisa de legislação e acervo de normas do escritório.

Separação obrigatória, e é ela que dita o formato das respostas daqui:

- **fonte jurídica original** — `url_fonte` (portal oficial do órgão) e o
  `texto_integral` obtido dele, nunca reescrito;
- **metadados** — tipo, número, ano, autoridade, derivados da URN (ver
  `services/lexml_urn.py`), nulos quando não foi possível derivar;
- **referência** — a `urn`, identificador jurídico citável e estável;
- **anotação do escritório** — texto do advogado sobre o caso, que vive em
  `lexml_norma_tenant` e nunca se mistura ao conteúdo da norma.

**Nenhum campo desta API carrega interpretação gerada por IA.** Se um dia
carregar, precisa vir num campo próprio, rotulado como sugestão — a regra é
que a interface nunca apresente saída de modelo como se fosse texto oficial
da norma.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.db.base import get_db
from app.dependencies import get_current_user
from app.models.lexml import LexmlNorma, LexmlNormaTenant
from app.models.user import User
from app.services import lexml_acervo

router = APIRouter(prefix="/lexml", tags=["lexml"])


class BuscaRequest(BaseModel):
    texto: str | None = None
    tipo_norma: str | None = None
    ano: int | None = None
    autoridade: str | None = None
    limite: int = Field(default=20, ge=1, le=100)
    # Permite ao chamador pedir só o acervo local (rápido, sem rede externa).
    consultar_fonte: bool = True


class VincularRequest(BaseModel):
    norma_id: uuid.UUID
    process_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    favorito: bool | None = None
    anotacao: str | None = None


@router.post("/buscar")
async def buscar_normas(
    body: BuscaRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Busca normas: acervo local primeiro, portal oficial quando faltar.

    `fonte_consultada`/`fonte_respondeu` distinguem "o acervo local já
    bastava" de "o portal foi chamado e não respondeu" — sem isso, indisponi-
    bilidade e ausência de resultado chegam à tela como a mesma coisa.
    """
    if not any([body.texto, body.tipo_norma, body.ano, body.autoridade]):
        raise ValidationError("Informe ao menos um critério de busca.")
    return await lexml_acervo.buscar(
        db, texto=body.texto, tipo_norma=body.tipo_norma, ano=body.ano,
        autoridade=body.autoridade, limite=body.limite,
        consultar_fonte=body.consultar_fonte,
    )


@router.get("/normas/{norma_id}")
async def obter_norma(
    norma_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Metadados de uma norma + o vínculo DESTE escritório com ela."""
    norma = (await db.execute(
        select(LexmlNorma).where(LexmlNorma.id == norma_id)
    )).scalar_one_or_none()
    if norma is None:
        raise NotFoundError("Norma", str(norma_id))

    vinculos = (await db.execute(
        select(LexmlNormaTenant).where(
            LexmlNormaTenant.tenant_id == current_user.tenant_id,
            LexmlNormaTenant.norma_id == norma_id,
        )
    )).scalars().all()

    return {
        **lexml_acervo.serializar_norma(norma, "acervo"),
        "vinculos": [
            {
                "id": str(v.id),
                "favorito": v.favorito,
                "process_id": str(v.process_id) if v.process_id else None,
                "document_id": str(v.document_id) if v.document_id else None,
                "anotacao": v.anotacao,
            }
            for v in vinculos
        ],
    }


@router.get("/normas/{norma_id}/texto")
async def obter_texto(
    norma_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Texto integral sob demanda, direto do portal oficial da norma.

    `origem` diz de onde o texto veio nesta resposta: `cache` (já buscado
    antes), `fonte` (buscado agora no órgão) ou `indisponivel` (não foi
    possível obter). Nunca é gerado nem resumido por IA.
    """
    resultado = await lexml_acervo.obter_texto_integral(db, norma_id=norma_id)
    if resultado is None:
        raise NotFoundError("Norma", str(norma_id))
    return resultado


@router.get("/acervo")
async def listar_acervo(
    favoritos: bool = Query(default=False),
    process_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Normas que ESTE escritório marcou/vinculou. Sempre tenant-scoped."""
    consulta = (
        select(LexmlNormaTenant, LexmlNorma)
        .join(LexmlNorma, LexmlNorma.id == LexmlNormaTenant.norma_id)
        .where(LexmlNormaTenant.tenant_id == current_user.tenant_id)
    )
    if favoritos:
        consulta = consulta.where(LexmlNormaTenant.favorito.is_(True))
    if process_id:
        consulta = consulta.where(LexmlNormaTenant.process_id == process_id)
    linhas = (await db.execute(consulta.order_by(LexmlNormaTenant.created_at.desc()))).all()
    return {
        "total": len(linhas),
        "resultados": [
            {
                **lexml_acervo.serializar_norma(norma, "acervo"),
                "vinculo": {
                    "id": str(v.id),
                    "favorito": v.favorito,
                    "process_id": str(v.process_id) if v.process_id else None,
                    "document_id": str(v.document_id) if v.document_id else None,
                    "anotacao": v.anotacao,
                },
            }
            for v, norma in linhas
        ],
    }


@router.post("/acervo")
async def vincular_norma(
    body: VincularRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Marca como favorito / vincula a processo / anota. Tenant-scoped."""
    norma = (await db.execute(
        select(LexmlNorma).where(LexmlNorma.id == body.norma_id)
    )).scalar_one_or_none()
    if norma is None:
        raise NotFoundError("Norma", str(body.norma_id))

    if body.process_id is not None:
        from app.models.process import LegalProcess
        processo = (await db.execute(
            select(LegalProcess.id).where(
                LegalProcess.id == body.process_id,
                LegalProcess.tenant_id == current_user.tenant_id,
            )
        )).scalar_one_or_none()
        if processo is None:
            raise NotFoundError("Processo", str(body.process_id))

    vinculo = await lexml_acervo.vincular(
        db, tenant_id=current_user.tenant_id, norma_id=body.norma_id,
        created_by=current_user.id, favorito=body.favorito,
        process_id=body.process_id, document_id=body.document_id,
        anotacao=body.anotacao,
    )
    await db.commit()
    return {
        "id": str(vinculo.id),
        "norma_id": str(vinculo.norma_id),
        "favorito": vinculo.favorito,
        "process_id": str(vinculo.process_id) if vinculo.process_id else None,
        "anotacao": vinculo.anotacao,
    }


@router.delete("/acervo/{norma_id}")
async def desvincular_norma(
    norma_id: uuid.UUID,
    process_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove o vínculo desta norma com este escritório."""
    removido = await lexml_acervo.desvincular(
        db, tenant_id=current_user.tenant_id, norma_id=norma_id, process_id=process_id,
    )
    if not removido:
        raise NotFoundError("Vínculo da norma", str(norma_id))
    await db.commit()
    return {"removido": True}
