"""Fase 217 — validação de CPF/CNPJ (Loja SERPRO, P1 recomendada pela
auditoria de APIs governamentais) + autofill de endereço por CEP
(BrasilAPI, pública/gratuita/não-governamental). Postgres real:
`consultar_cpf`/`consultar_cnpj`/`consultar_cep` monkeypatchados (nunca
bate rede real) — confirma que validação bem-sucedida grava auditoria em
`GovRegistryLookup`, que indisponibilidade externa nunca vira 500 (sempre
`valido: None`, fail-soft), e isolamento cross-tenant do log de
auditoria."""
import uuid

import pytest
from fastapi import HTTPException

import app.api.v1.clients as clients_mod
from app.db.base import AsyncSessionLocal
from app.models.gov_registry_lookup import GovRegistryLookup
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.anyio


class _CurrentUser:
    def __init__(self, tenant_id, uid=None):
        self.tenant_id = tenant_id
        self.id = uid or uuid.uuid4()


@pytest.fixture
async def cenario():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 217", slug=f"teste-217-{uuid.uuid4().hex[:8]}")
        outro_tenant = Tenant(name="Outro 217", slug=f"outro-217-{uuid.uuid4().hex[:8]}")
        db.add_all([tenant, outro_tenant])
        await db.flush()
        user = User(
            email=f"user-217-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Usuario Teste 217", role="ADMIN", tenant_id=tenant.id,
        )
        db.add(user)
        await db.commit()
        ids = {"tenant": tenant.id, "outro_tenant": outro_tenant.id, "user": user.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(GovRegistryLookup.__table__.delete().where(
            GovRegistryLookup.tenant_id.in_([ids["tenant"], ids["outro_tenant"]])
        ))
        await db.execute(User.__table__.delete().where(User.id == ids["user"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id.in_([ids["tenant"], ids["outro_tenant"]])))
        await db.commit()


async def test_validacao_bem_sucedida_grava_auditoria(cenario, monkeypatch):
    async def fake_consultar_cpf(cpf):
        return {"nome": "Fulano de Tal", "situacao": {"nome": "REGULAR"}}
    monkeypatch.setattr(clients_mod, "consultar_cpf", fake_consultar_cpf)

    async with AsyncSessionLocal() as db:
        resp = await clients_mod.validar_documento(
            clients_mod.ValidarDocumentoBody(tipo="cpf", valor="12345678901"),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
    assert resp["valido"] is True
    assert resp["nome_ou_razao_social"] == "Fulano de Tal"
    assert resp["situacao_cadastral"] == "REGULAR"

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        rows = (await db.execute(
            select(GovRegistryLookup).where(GovRegistryLookup.tenant_id == cenario["tenant"])
        )).scalars().all()
    assert len(rows) == 1
    assert rows[0].tipo_consulta == "CPF"
    assert "Fulano de Tal" in rows[0].resultado_resumo
    assert rows[0].documento_consultado != "12345678901"  # criptografado, não plaintext


async def test_indisponibilidade_externa_nao_quebra_nunca_500(cenario, monkeypatch):
    async def fake_consultar_cnpj(cnpj):
        return None  # simula timeout/circuito aberto/não configurado
    monkeypatch.setattr(clients_mod, "consultar_cnpj", fake_consultar_cnpj)

    async with AsyncSessionLocal() as db:
        resp = await clients_mod.validar_documento(
            clients_mod.ValidarDocumentoBody(tipo="cnpj", valor="12345678000199"),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
    assert resp["valido"] is None
    assert resp["mensagem"] is not None


async def test_tipo_invalido_rejeitado(cenario):
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc_info:
            await clients_mod.validar_documento(
                clients_mod.ValidarDocumentoBody(tipo="rg", valor="123"),
                current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
            )
    assert exc_info.value.status_code == 422


async def test_isolamento_cross_tenant_auditoria(cenario, monkeypatch):
    async def fake_consultar_cpf(cpf):
        return {"nome": "Vazamento Teste"}
    monkeypatch.setattr(clients_mod, "consultar_cpf", fake_consultar_cpf)

    async with AsyncSessionLocal() as db:
        await clients_mod.validar_documento(
            clients_mod.ValidarDocumentoBody(tipo="cpf", valor="98765432100"),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        rows_outro = (await db.execute(
            select(GovRegistryLookup).where(GovRegistryLookup.tenant_id == cenario["outro_tenant"])
        )).scalars().all()
    assert rows_outro == []


async def test_formato_invalido_rejeitado_sem_bater_serpro_nem_gravar(cenario, monkeypatch):
    """Fase 220 (achado da Fase 219) — antes desta fase, `body.valor` bruto
    (sem validar tamanho) era cifrado e gravado direto em
    `documento_consultado` (String(255)), causando 500 pra input longo.
    Agora o formato é validado ANTES de bater SERPRO ou tocar o banco."""
    async def fake_consultar_cpf(cpf):
        raise AssertionError("consultar_cpf não deveria ser chamado com formato inválido")
    monkeypatch.setattr(clients_mod, "consultar_cpf", fake_consultar_cpf)

    async with AsyncSessionLocal() as db:
        resp = await clients_mod.validar_documento(
            clients_mod.ValidarDocumentoBody(tipo="cpf", valor="1" * 200),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
    assert resp["valido"] is False
    assert resp["mensagem"] == "Formato de CPF/CNPJ inválido."

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        rows = (await db.execute(
            select(GovRegistryLookup).where(GovRegistryLookup.tenant_id == cenario["tenant"])
        )).scalars().all()
    assert rows == []


async def test_cep_nao_encontrado_devolve_campos_nulos_nao_erro(cenario, monkeypatch):
    async def fake_consultar_cep(cep):
        return None
    monkeypatch.setattr(clients_mod, "_consultar_cep_externa", fake_consultar_cep)

    resp = await clients_mod.consultar_cep_endpoint(
        clients_mod.ConsultarCepBody(cep="00000000"),
        current_user=_CurrentUser(cenario["tenant"], cenario["user"]),
    )
    assert resp == {"logradouro": None, "bairro": None, "cidade": None, "uf": None}


async def test_cep_encontrado_devolve_endereco(cenario, monkeypatch):
    async def fake_consultar_cep(cep):
        return {"logradouro": "Av. Paulista", "bairro": "Bela Vista", "cidade": "São Paulo", "uf": "SP"}
    monkeypatch.setattr(clients_mod, "_consultar_cep_externa", fake_consultar_cep)

    resp = await clients_mod.consultar_cep_endpoint(
        clients_mod.ConsultarCepBody(cep="01310100"),
        current_user=_CurrentUser(cenario["tenant"], cenario["user"]),
    )
    assert resp["cidade"] == "São Paulo"
    assert resp["uf"] == "SP"
