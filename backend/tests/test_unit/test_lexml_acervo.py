"""Acervo LexML com Postgres real — upsert por URN, backfill e isolamento.

Usa `sessao_isolada()` (engine próprio + NullPool dentro do loop do teste),
pelo motivo já catalogado no projeto: o engine de produção é singleton de
módulo e o pytest-asyncio cria um loop por teste.
"""
import uuid

import pytest
from sqlalchemy import select

from app.models.jurisprudencia_ingerida import JurisprudenciaIngerida
from app.models.lexml import LexmlNorma, LexmlNormaTenant
from app.models.tenant import Tenant
from app.services.lexml_acervo import (
    backfill_de_jurisprudencia_ingerida,
    desvincular,
    registrar_texto_integral,
    upsert_norma,
    vincular,
)
from tests.db_isolada import sessao_isolada

_CDC = "urn:lex:br:federal:lei:1990-09-11;8078"


async def _limpar(db, urns: list[str]):
    for urn in urns:
        norma = (await db.execute(select(LexmlNorma).where(LexmlNorma.urn == urn))).scalar_one_or_none()
        if norma:
            await db.execute(
                LexmlNormaTenant.__table__.delete().where(LexmlNormaTenant.norma_id == norma.id)
            )
            await db.delete(norma)
    await db.commit()


@pytest.mark.asyncio
async def test_upsert_deriva_campos_da_urn_e_nao_duplica():
    urn = "urn:lex:br:federal:lei:1990-09-11;8078"
    async with sessao_isolada() as db:
        await _limpar(db, [urn])
        try:
            criada = await upsert_norma(db, urn=urn, titulo="Código de Defesa do Consumidor")
            await db.commit()
            assert criada.tipo_norma == "Lei"
            assert criada.ano == 1990
            assert criada.numero == "8078"

            # Mesma URN em outra grafia → atualiza, não duplica
            de_novo = await upsert_norma(db, urn="  URN:LEX:BR:FEDERAL:LEI:1990-09-11;8078 ")
            await db.commit()
            assert de_novo.id == criada.id

            total = (await db.execute(
                select(LexmlNorma).where(LexmlNorma.urn == urn)
            )).scalars().all()
            assert len(total) == 1
        finally:
            await _limpar(db, [urn])


@pytest.mark.asyncio
async def test_upsert_nao_apaga_metadado_que_ja_existia():
    """Uma busca que devolveu menos informação que a ingestão anterior não
    pode zerar o que já se sabia."""
    urn = "urn:lex:br:federal:decreto:2021-01-15;10001"
    async with sessao_isolada() as db:
        await _limpar(db, [urn])
        try:
            await upsert_norma(db, urn=urn, titulo="Decreto Completo", ementa="Ementa original")
            await db.commit()
            await upsert_norma(db, urn=urn)  # sem título nem ementa
            await db.commit()
            norma = (await db.execute(select(LexmlNorma).where(LexmlNorma.urn == urn))).scalar_one()
            assert norma.titulo == "Decreto Completo"
            assert norma.ementa == "Ementa original"
        finally:
            await _limpar(db, [urn])


@pytest.mark.asyncio
async def test_urn_invalida_nao_cria_linha():
    async with sessao_isolada() as db:
        assert await upsert_norma(db, urn="lei 8078 de 1990") is None
        assert await upsert_norma(db, urn="") is None


@pytest.mark.asyncio
async def test_texto_integral_e_gravado_com_a_data():
    urn = "urn:lex:br:federal:lei:2021-04-01;14133"
    async with sessao_isolada() as db:
        await _limpar(db, [urn])
        try:
            await upsert_norma(db, urn=urn, titulo="Nova Lei de Licitações")
            await db.commit()
            await registrar_texto_integral(db, urn=urn, texto="Art. 1º Esta Lei estabelece...")
            await db.commit()
            norma = (await db.execute(select(LexmlNorma).where(LexmlNorma.urn == urn))).scalar_one()
            assert norma.texto_integral.startswith("Art. 1º")
            assert norma.texto_obtido_em is not None
        finally:
            await _limpar(db, [urn])


@pytest.mark.asyncio
async def test_backfill_e_idempotente_e_conta_honesto():
    """Segunda execução não pode inflar `criadas` — é exatamente a classe de
    bug ("falha/no-op aparecendo como sucesso") que este projeto já corrigiu
    em quatro lugares."""
    urn_ok = "urn:lex:br:federal:lei:1988-10-05;99999"
    urn_ruim = "isto-nao-e-uma-urn"
    async with sessao_isolada() as db:
        await _limpar(db, [urn_ok])
        await db.execute(
            JurisprudenciaIngerida.__table__.delete().where(
                JurisprudenciaIngerida.fonte_documento_id.in_([urn_ok, urn_ruim])
            )
        )
        db.add(JurisprudenciaIngerida(
            fonte="lexml_legislacao", fonte_documento_id=urn_ok,
            collection_alvo="legislacao", status="EMBEDDED",
            metadata_extraida={"titulo": "Lei de Teste", "url": "https://www.planalto.gov.br/x"},
        ))
        db.add(JurisprudenciaIngerida(
            fonte="lexml_legislacao", fonte_documento_id=urn_ruim,
            collection_alvo="legislacao", status="EMBEDDED", metadata_extraida={},
        ))
        await db.commit()
        try:
            primeira = await backfill_de_jurisprudencia_ingerida(db)
            assert primeira["criadas"] >= 1
            assert primeira["urn_invalida"] >= 1, "a URN lixo tem que ser contada como inválida"

            segunda = await backfill_de_jurisprudencia_ingerida(db)
            assert segunda["criadas"] == 0, "rodar de novo não pode recriar"
            assert segunda["ja_existentes"] >= 1

            norma = (await db.execute(select(LexmlNorma).where(LexmlNorma.urn == urn_ok))).scalar_one()
            assert norma.titulo == "Lei de Teste"
            assert norma.ano == 1988  # derivado da URN, não do metadata pobre
        finally:
            await db.execute(
                JurisprudenciaIngerida.__table__.delete().where(
                    JurisprudenciaIngerida.fonte_documento_id.in_([urn_ok, urn_ruim])
                )
            )
            await _limpar(db, [urn_ok])


@pytest.mark.asyncio
async def test_vinculo_e_isolado_por_tenant():
    """A norma é compartilhada; o vínculo com ela, nunca."""
    urn = "urn:lex:br:federal:lei:2002-01-10;10406"
    async with sessao_isolada() as db:
        await _limpar(db, [urn])
        t1 = Tenant(name="Escritorio Um", slug=f"lexml-t1-{uuid.uuid4().hex[:8]}")
        t2 = Tenant(name="Escritorio Dois", slug=f"lexml-t2-{uuid.uuid4().hex[:8]}")
        db.add_all([t1, t2])
        await db.flush()
        try:
            norma = await upsert_norma(db, urn=urn, titulo="Código Civil")
            await vincular(db, tenant_id=t1.id, norma_id=norma.id,
                           favorito=True, anotacao="Usar na ação de rescisão")
            await db.commit()

            do_t1 = (await db.execute(select(LexmlNormaTenant).where(
                LexmlNormaTenant.tenant_id == t1.id))).scalars().all()
            do_t2 = (await db.execute(select(LexmlNormaTenant).where(
                LexmlNormaTenant.tenant_id == t2.id))).scalars().all()
            assert len(do_t1) == 1 and do_t1[0].anotacao == "Usar na ação de rescisão"
            assert do_t2 == [], "o outro escritório não pode ver o vínculo"

            # A MESMA norma é visível para os dois — é compartilhada
            assert (await db.execute(select(LexmlNorma).where(
                LexmlNorma.urn == urn))).scalar_one().id == norma.id

            assert await desvincular(db, tenant_id=t1.id, norma_id=norma.id) is True
            assert await desvincular(db, tenant_id=t1.id, norma_id=norma.id) is False
            await db.commit()
        finally:
            await db.execute(Tenant.__table__.delete().where(Tenant.id.in_([t1.id, t2.id])))
            await _limpar(db, [urn])
