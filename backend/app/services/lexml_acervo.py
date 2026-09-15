"""Acervo LexML — persistência de normas e a relação do escritório com elas.

Camada de negócio entre os endpoints e o banco. Duas responsabilidades:

1. **Upsert por URN** — a URN é a chave natural; a mesma norma vista duas
   vezes (pela sincronização diária ou por uma busca ao vivo) atualiza a
   linha existente em vez de duplicar.
2. **Backfill** — o sistema já ingeriu normas antes desta tabela existir. O
   registro delas está em `JurisprudenciaIngerida` (fonte `lexml_legislacao`),
   com `fonte_documento_id` = URN e um `metadata_extraida` pobre
   (`{titulo, tipo_norma, url}`). O que der para derivar da URN é derivado; o
   resto fica nulo até a próxima sincronização enriquecer.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import get_redis

from app.models.jurisprudencia_ingerida import JurisprudenciaIngerida
from app.models.lexml import LexmlNorma, LexmlNormaTenant
from app.services.lexml_urn import derivar_campos_da_urn, normalizar_urn, validar_urn

log = structlog.get_logger()

FONTE_LEGISLACAO = "lexml_legislacao"


async def upsert_norma(
    db: AsyncSession,
    *,
    urn: str,
    titulo: str | None = None,
    ementa: str | None = None,
    url_fonte: str | None = None,
    metadata_extra: dict | None = None,
) -> LexmlNorma | None:
    """Cria ou atualiza uma norma pela URN. `None` se a URN for inválida.

    Só sobrescreve campo com valor não-vazio — uma busca que devolveu menos
    metadado que a ingestão anterior não pode apagar o que já se sabia.
    """
    normalizada = normalizar_urn(urn)
    if not validar_urn(normalizada):
        log.warning("lexml_urn_invalida", urn=(urn or "")[:120])
        return None

    existente = (await db.execute(
        select(LexmlNorma).where(LexmlNorma.urn == normalizada)
    )).scalar_one_or_none()

    derivados = derivar_campos_da_urn(normalizada)
    data_pub = derivados.pop("data_publicacao", None)

    if existente is None:
        norma = LexmlNorma(
            urn=normalizada,
            titulo=titulo,
            ementa=ementa,
            url_fonte=url_fonte,
            metadata_json=metadata_extra or {},
            **derivados,
        )
        if data_pub:
            norma.data_publicacao = datetime.fromisoformat(data_pub).replace(tzinfo=timezone.utc)
        db.add(norma)
        await db.flush()
        return norma

    # Atualização conservadora: só preenche o que veio preenchido.
    if titulo:
        existente.titulo = titulo
    if ementa:
        existente.ementa = ementa
    if url_fonte:
        existente.url_fonte = url_fonte
    for campo, valor in derivados.items():
        if valor and not getattr(existente, campo, None):
            setattr(existente, campo, valor)
    if data_pub and not existente.data_publicacao:
        existente.data_publicacao = datetime.fromisoformat(data_pub).replace(tzinfo=timezone.utc)
    if metadata_extra:
        existente.metadata_json = {**(existente.metadata_json or {}), **metadata_extra}
    await db.flush()
    return existente


async def registrar_texto_integral(db: AsyncSession, *, urn: str, texto: str) -> None:
    """Guarda o texto buscado sob demanda, com a data da obtenção."""
    normalizada = normalizar_urn(urn)
    norma = (await db.execute(
        select(LexmlNorma).where(LexmlNorma.urn == normalizada)
    )).scalar_one_or_none()
    if norma is None:
        return
    norma.texto_integral = texto
    norma.texto_obtido_em = datetime.now(timezone.utc)
    await db.flush()


async def backfill_de_jurisprudencia_ingerida(db: AsyncSession, *, limite: int = 5000) -> dict:
    """Popula `lexml_normas` a partir do que a sincronização diária já ingeriu.

    Idempotente: rodar duas vezes não duplica nem sobrescreve com pior. Conta
    o que criou, o que já existia e o que tinha URN inválida — sem inflar o
    número de sucesso, que é justamente a classe de bug que este projeto já
    corrigiu várias vezes.
    """
    linhas = (await db.execute(
        select(JurisprudenciaIngerida)
        .where(JurisprudenciaIngerida.fonte == FONTE_LEGISLACAO)
        .limit(limite)
    )).scalars().all()

    criadas = existentes = invalidas = 0
    for linha in linhas:
        urn = linha.fonte_documento_id
        if not validar_urn(urn):
            invalidas += 1
            continue
        meta = linha.metadata_extraida or {}
        ja_existia = (await db.execute(
            select(LexmlNorma.id).where(LexmlNorma.urn == normalizar_urn(urn))
        )).scalar_one_or_none() is not None
        norma = await upsert_norma(
            db,
            urn=urn,
            titulo=meta.get("titulo"),
            url_fonte=meta.get("url"),
            metadata_extra={"origem_backfill": "jurisprudencia_ingerida"},
        )
        if norma is None:
            invalidas += 1
        elif ja_existia:
            existentes += 1
        else:
            criadas += 1

    await db.commit()
    resultado = {
        "lidas": len(linhas), "criadas": criadas,
        "ja_existentes": existentes, "urn_invalida": invalidas,
    }
    log.info("lexml_backfill_concluido", **resultado)
    return resultado


# ─── Relação do escritório com a norma ───────────────────────────────────────

async def vincular(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    norma_id: uuid.UUID,
    created_by: uuid.UUID | None = None,
    favorito: bool | None = None,
    process_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    anotacao: str | None = None,
) -> LexmlNormaTenant:
    """Cria ou atualiza o vínculo desta norma com ESTE escritório.

    A unique é `(tenant_id, norma_id, process_id)`: a mesma norma pode estar
    vinculada a vários processos do mesmo escritório, e uma vez "solta"
    (favorito sem processo) — daí `process_id` fazer parte da chave.
    """
    existente = (await db.execute(
        select(LexmlNormaTenant).where(
            LexmlNormaTenant.tenant_id == tenant_id,
            LexmlNormaTenant.norma_id == norma_id,
            LexmlNormaTenant.process_id == process_id,
        )
    )).scalar_one_or_none()

    if existente is None:
        existente = LexmlNormaTenant(
            tenant_id=tenant_id, norma_id=norma_id, created_by=created_by,
            favorito=bool(favorito), process_id=process_id,
            document_id=document_id, anotacao=anotacao,
        )
        db.add(existente)
    else:
        if favorito is not None:
            existente.favorito = favorito
        if document_id is not None:
            existente.document_id = document_id
        if anotacao is not None:
            existente.anotacao = anotacao
    await db.flush()
    return existente


async def desvincular(
    db: AsyncSession, *, tenant_id: uuid.UUID, norma_id: uuid.UUID,
    process_id: uuid.UUID | None = None,
) -> bool:
    """Remove o vínculo. `True` se havia algo para remover."""
    alvo = (await db.execute(
        select(LexmlNormaTenant).where(
            LexmlNormaTenant.tenant_id == tenant_id,
            LexmlNormaTenant.norma_id == norma_id,
            LexmlNormaTenant.process_id == process_id,
        )
    )).scalar_one_or_none()
    if alvo is None:
        return False
    await db.delete(alvo)
    await db.flush()
    return True


# ─── Busca: cache → acervo local → SRU ao vivo ───────────────────────────────

CACHE_TTL_SEGUNDOS = 600


def _chave_cache(texto: str, tipo: str | None, ano: int | None,
                 autoridade: str | None, limite: int) -> str:
    """Chave de cache da busca. Sem `tenant_id` de propósito: o acervo é
    compartilhado e nada do que esta busca devolve é do escritório — o
    vínculo (favorito/anotação) é consultado à parte, por tenant."""
    bruto = json.dumps(
        {"texto": texto, "tipo": tipo, "ano": ano, "autoridade": autoridade, "limite": limite},
        sort_keys=True,
    )
    return f"lexml:busca:{hashlib.sha256(bruto.encode()).hexdigest()}"


def serializar_norma(norma: LexmlNorma, origem: str) -> dict:
    return {
        "id": str(norma.id),
        "urn": norma.urn,
        "titulo": norma.titulo,
        "ementa": norma.ementa,
        "tipo_norma": norma.tipo_norma,
        "numero": norma.numero,
        "ano": norma.ano,
        "autoridade": norma.autoridade,
        "localidade": norma.localidade,
        "url_fonte": norma.url_fonte,
        "tem_texto_integral": norma.texto_integral is not None,
        "texto_obtido_em": norma.texto_obtido_em.isoformat() if norma.texto_obtido_em else None,
        # De onde ESTA linha veio nesta resposta. O usuário precisa saber se
        # está vendo o acervo já conhecido ou algo que acabou de chegar do
        # portal oficial — são níveis de frescor diferentes.
        "origem": origem,
    }


async def buscar_no_acervo(
    db: AsyncSession, *, texto: str | None = None, tipo_norma: str | None = None,
    ano: int | None = None, autoridade: str | None = None, limite: int = 20,
) -> list[LexmlNorma]:
    """Busca no acervo local (Postgres). `ano`/`autoridade` são filtrados AQUI,
    não na CQL — os índices correspondentes do SRU nunca foram confirmados
    respondendo, e mandar um índice inexistente pode derrubar a busca inteira
    (ver `montar_query_cql`)."""
    consulta = select(LexmlNorma)
    termo = " ".join((texto or "").split()).strip()
    if termo:
        padrao = f"%{termo}%"
        consulta = consulta.where(or_(
            LexmlNorma.titulo.ilike(padrao),
            LexmlNorma.ementa.ilike(padrao),
            LexmlNorma.urn.ilike(padrao),
        ))
    if tipo_norma:
        consulta = consulta.where(LexmlNorma.tipo_norma.ilike(tipo_norma))
    if ano:
        consulta = consulta.where(LexmlNorma.ano == ano)
    if autoridade:
        consulta = consulta.where(LexmlNorma.autoridade.ilike(f"%{autoridade}%"))
    consulta = consulta.order_by(LexmlNorma.ano.desc().nullslast(), LexmlNorma.titulo).limit(limite)
    return list((await db.execute(consulta)).scalars().all())


async def buscar(
    db: AsyncSession, *, texto: str | None = None, tipo_norma: str | None = None,
    ano: int | None = None, autoridade: str | None = None, limite: int = 20,
    consultar_fonte: bool = True,
) -> dict:
    """Busca orquestrada: cache → acervo local → SRU ao vivo.

    O SRU só é consultado quando o acervo local não preenche o limite pedido —
    é rede externa num caminho síncrono de usuário. O que vier de lá é
    persistido (UPSERT por URN), então a mesma busca fica local na próxima vez.

    `fonte_consultada` diz se o portal foi de fato chamado nesta resposta:
    sem isso, "o LexML está fora do ar" e "o acervo local já bastava" chegam
    à tela como a mesma coisa — o mesmo defeito de fail-soft que este projeto
    já corrigiu no DataJud e no Comunica.
    """
    limite = max(1, min(int(limite or 20), 100))
    chave = _chave_cache(texto or "", tipo_norma, ano, autoridade, limite)

    redis = await get_redis()
    if redis:
        try:
            em_cache = await redis.get(chave)
            if em_cache:
                return json.loads(em_cache)
        except Exception as exc:
            log.warning("lexml_cache_leitura_falhou", error=str(exc))

    locais = await buscar_no_acervo(
        db, texto=texto, tipo_norma=tipo_norma, ano=ano, autoridade=autoridade, limite=limite,
    )
    resultados = [serializar_norma(n, "acervo") for n in locais]
    vistas = {n.urn for n in locais}

    fonte_consultada = False
    fonte_respondeu = False
    if consultar_fonte and texto and len(resultados) < limite:
        from app.integrations.lexml.client import buscar_normas

        fonte_consultada = True
        registros = await buscar_normas(texto, tipo_norma, limite)
        fonte_respondeu = bool(registros)
        for registro in registros:
            urn_normalizada = normalizar_urn(registro.get("urn"))
            if not urn_normalizada or urn_normalizada in vistas:
                continue
            norma = await upsert_norma(
                db,
                urn=registro["urn"],
                titulo=registro.get("titulo"),
                url_fonte=registro.get("url"),
                metadata_extra={"origem": "busca_sru"},
            )
            if norma is None:
                continue
            vistas.add(norma.urn)
            # Os filtros não-provados em CQL (ano/autoridade) valem também
            # para o que veio do portal — senão a mesma busca devolveria
            # conjuntos diferentes conforme a origem de cada linha.
            if ano and norma.ano != ano:
                continue
            if autoridade and (norma.autoridade or "").lower() != autoridade.lower():
                continue
            resultados.append(serializar_norma(norma, "lexml"))
            if len(resultados) >= limite:
                break
        await db.commit()

    resposta = {
        "total": len(resultados),
        "resultados": resultados[:limite],
        "fonte_consultada": fonte_consultada,
        "fonte_respondeu": fonte_respondeu,
    }
    if redis:
        try:
            await redis.set(chave, json.dumps(resposta), ex=CACHE_TTL_SEGUNDOS)
        except Exception as exc:
            log.warning("lexml_cache_escrita_falhou", error=str(exc))
    return resposta


async def obter_texto_integral(db: AsyncSession, *, norma_id: uuid.UUID) -> dict | None:
    """Texto integral sob demanda: devolve o cacheado se já houver, senão
    busca na fonte oficial e guarda. `None` se a norma não existir.

    O texto não é replicado em massa (decisão do dono do produto): o LexML é
    agregador de metadado, o texto vive no órgão de origem, e replicar o
    acervo inteiro num produto comercial é a mesma classe de questão já
    registrada em `docs/juridico/DATAJUD_TERMO_DE_USO.md`.
    """
    norma = (await db.execute(
        select(LexmlNorma).where(LexmlNorma.id == norma_id)
    )).scalar_one_or_none()
    if norma is None:
        return None
    if norma.texto_integral:
        return {
            "urn": norma.urn, "titulo": norma.titulo, "texto": norma.texto_integral,
            "url_fonte": norma.url_fonte, "origem": "cache",
            "obtido_em": norma.texto_obtido_em.isoformat() if norma.texto_obtido_em else None,
        }
    if not norma.url_fonte:
        return {
            "urn": norma.urn, "titulo": norma.titulo, "texto": None,
            "url_fonte": None, "origem": "indisponivel", "obtido_em": None,
        }

    from app.integrations.lexml.client import baixar_texto_norma

    texto = await baixar_texto_norma(norma.url_fonte)
    if not texto:
        return {
            "urn": norma.urn, "titulo": norma.titulo, "texto": None,
            "url_fonte": norma.url_fonte, "origem": "indisponivel", "obtido_em": None,
        }
    norma.texto_integral = texto
    norma.texto_obtido_em = datetime.now(timezone.utc)
    await db.commit()
    return {
        "urn": norma.urn, "titulo": norma.titulo, "texto": texto,
        "url_fonte": norma.url_fonte, "origem": "fonte",
        "obtido_em": norma.texto_obtido_em.isoformat(),
    }
