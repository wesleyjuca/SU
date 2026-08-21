"""Fase 207.3 — ação em lote sobre processos: POST /processes/bulk-update.
Postgres real: confirma atualização de situação/responsável em múltiplos
processos de uma vez, isolamento cross-tenant (processo de outro tenant é
silenciosamente excluído da contagem, não erro), e as validações de entrada
(lista vazia, teto de 200, nem situação nem responsável informados,
responsável fora do tenant)."""
import uuid

import pytest
from fastapi import HTTPException

from app.api.v1.processes import BulkProcessUpdate, bulk_update_processes
from app.db.base import AsyncSessionLocal
from app.models.process import LegalProcess
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.anyio


class _CurrentUser:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


@pytest.fixture
async def cenario():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 207.3", slug=f"teste-207-3-{uuid.uuid4().hex[:8]}")
        outro_tenant = Tenant(name="Outro 207.3", slug=f"outro-207-3-{uuid.uuid4().hex[:8]}")
        db.add_all([tenant, outro_tenant])
        await db.flush()
        adv = User(
            email=f"adv-207-3-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Advogado Teste 207.3", role="ADVOGADO", tenant_id=tenant.id,
        )
        adv_outro_tenant = User(
            email=f"adv-outro-207-3-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Advogado Outro Tenant", role="ADVOGADO", tenant_id=outro_tenant.id,
        )
        db.add_all([adv, adv_outro_tenant])
        await db.flush()

        procs = [
            LegalProcess(
                numero_cnj=f"{uuid.uuid4().hex[:7]}-00.2026.0.00.0000", tribunal="TJSP",
                tenant_id=tenant.id, responsavel_id=adv.id, situacao="ATIVO",
            )
            for _ in range(3)
        ]
        proc_outro_tenant = LegalProcess(
            numero_cnj=f"{uuid.uuid4().hex[:7]}-00.2026.0.00.0000", tribunal="TJSP",
            tenant_id=outro_tenant.id, responsavel_id=adv_outro_tenant.id, situacao="ATIVO",
        )
        db.add_all(procs + [proc_outro_tenant])
        await db.commit()
        ids = {
            "tenant": tenant.id, "outro_tenant": outro_tenant.id,
            "adv": adv.id, "adv_outro_tenant": adv_outro_tenant.id,
            "procs": [p.id for p in procs], "proc_outro_tenant": proc_outro_tenant.id,
        }
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(LegalProcess.__table__.delete().where(
            LegalProcess.tenant_id.in_([ids["tenant"], ids["outro_tenant"]])
        ))
        await db.execute(User.__table__.delete().where(User.id.in_([ids["adv"], ids["adv_outro_tenant"]])))
        await db.execute(Tenant.__table__.delete().where(Tenant.id.in_([ids["tenant"], ids["outro_tenant"]])))
        await db.commit()


async def test_atualiza_situacao_de_varios_processos(cenario):
    async with AsyncSessionLocal() as db:
        resp = await bulk_update_processes(
            body=BulkProcessUpdate(process_ids=[str(p) for p in cenario["procs"]], situacao="ARQUIVADO"),
            current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    assert resp == {"atualizados": 3, "solicitados": 3}
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            LegalProcess.__table__.select().where(LegalProcess.id.in_(cenario["procs"]))
        )).all()
    assert all(r.situacao == "ARQUIVADO" for r in rows)


async def test_processo_de_outro_tenant_nao_conta(cenario):
    async with AsyncSessionLocal() as db:
        resp = await bulk_update_processes(
            body=BulkProcessUpdate(
                process_ids=[str(cenario["procs"][0]), str(cenario["proc_outro_tenant"])],
                situacao="SUSPENSO",
            ),
            current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    assert resp == {"atualizados": 1, "solicitados": 2}
    async with AsyncSessionLocal() as db:
        outro = (await db.execute(
            LegalProcess.__table__.select().where(LegalProcess.id == cenario["proc_outro_tenant"])
        )).first()
    assert outro.situacao == "ATIVO"  # intocado


async def test_responsavel_valido_atualiza_todos(cenario):
    async with AsyncSessionLocal() as db:
        resp = await bulk_update_processes(
            body=BulkProcessUpdate(
                process_ids=[str(p) for p in cenario["procs"]], responsavel_id=str(cenario["adv"]),
            ),
            current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    assert resp["atualizados"] == 3


async def test_responsavel_de_outro_tenant_rejeitado(cenario):
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc_info:
            await bulk_update_processes(
                body=BulkProcessUpdate(
                    process_ids=[str(cenario["procs"][0])], responsavel_id=str(cenario["adv_outro_tenant"]),
                ),
                current_user=_CurrentUser(cenario["tenant"]), db=db,
            )
    assert exc_info.value.status_code == 422


async def test_lista_vazia_rejeitada(cenario):
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc_info:
            await bulk_update_processes(
                body=BulkProcessUpdate(process_ids=[], situacao="ARQUIVADO"),
                current_user=_CurrentUser(cenario["tenant"]), db=db,
            )
    assert exc_info.value.status_code == 422


async def test_mais_de_200_ids_rejeitado(cenario):
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc_info:
            await bulk_update_processes(
                body=BulkProcessUpdate(
                    process_ids=[str(uuid.uuid4()) for _ in range(201)], situacao="ARQUIVADO",
                ),
                current_user=_CurrentUser(cenario["tenant"]), db=db,
            )
    assert exc_info.value.status_code == 422


async def test_nem_situacao_nem_responsavel_rejeitado(cenario):
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc_info:
            await bulk_update_processes(
                body=BulkProcessUpdate(process_ids=[str(cenario["procs"][0])]),
                current_user=_CurrentUser(cenario["tenant"]), db=db,
            )
    assert exc_info.value.status_code == 422
