"""Fase 233 — usuário reportou "o cadastro de clientes não está
capturando coordenadas". Leitura de `clients.py` mostrou que
`_geocodificar_endereco()` já é chamado em `create_client`/
`update_client` (mesmo padrão de `Tenant`, Fase 230) — mas a
disciplina desta sessão é nunca confiar só em leitura de código.
Este teste prova empiricamente, com Postgres real e
`_consultar_cep_externa` monkeypatchado (mesmo padrão da Fase 217,
`test_client_document_validation_fase217.py`), que `POST`/`PUT
/clients` persistem `latitude`/`longitude` reais quando o endereço
tem CEP."""
import uuid

import pytest

import app.api.v1.clients as clients_mod
from app.db.base import AsyncSessionLocal
from app.models.client import Client
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
        tenant = Tenant(name="Tenant 233", slug=f"teste-233-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        user = User(
            email=f"user-233-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Usuario Teste 233", role="ADMIN", tenant_id=tenant.id,
        )
        db.add(user)
        await db.commit()
        ids = {"tenant": tenant.id, "user": user.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(Client.__table__.delete().where(Client.tenant_id == ids["tenant"]))
        await db.execute(User.__table__.delete().where(User.id == ids["user"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == ids["tenant"]))
        await db.commit()


def _fake_consultar_cep():
    async def fake(cep):
        return {
            "logradouro": "Av. Paulista", "bairro": "Bela Vista",
            "cidade": "São Paulo", "uf": "SP",
            "latitude": -23.5613, "longitude": -46.6564,
        }
    return fake


async def test_create_client_com_cep_geocodifica(cenario, monkeypatch):
    monkeypatch.setattr(clients_mod, "_consultar_cep_externa", _fake_consultar_cep())

    async with AsyncSessionLocal() as db:
        resp = await clients_mod.create_client(
            clients_mod.ClientCreate(
                tipo="PF", nome_completo="Cliente Geocodificado",
                endereco_json={"cep": "01310-100", "logradouro": "", "bairro": "", "cidade": "", "uf": ""},
            ),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
        await db.commit()

    assert resp.endereco_json["latitude"] == -23.5613
    assert resp.endereco_json["longitude"] == -46.6564

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        row = (await db.execute(
            select(Client).where(Client.tenant_id == cenario["tenant"])
        )).scalar_one()
    assert row.endereco_json["latitude"] == -23.5613
    assert row.endereco_json["longitude"] == -46.6564


async def test_update_client_com_cep_geocodifica(cenario, monkeypatch):
    """Cliente criado SEM endereço, depois editado com CEP — mesmo
    fluxo de 'editar cliente existente e adicionar endereço' que o
    usuário testaria na tela de Clientes."""
    async with AsyncSessionLocal() as db:
        created = await clients_mod.create_client(
            clients_mod.ClientCreate(tipo="PF", nome_completo="Cliente Sem Endereco"),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
        await db.commit()
        client_id = created.id

    monkeypatch.setattr(clients_mod, "_consultar_cep_externa", _fake_consultar_cep())

    async with AsyncSessionLocal() as db:
        updated = await clients_mod.update_client(
            client_id,
            clients_mod.ClientCreate(
                tipo="PF", nome_completo="Cliente Sem Endereco",
                endereco_json={"cep": "01310-100", "logradouro": "", "bairro": "", "cidade": "", "uf": ""},
            ),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
        await db.commit()

    assert updated.endereco_json["latitude"] == -23.5613
    assert updated.endereco_json["longitude"] == -46.6564

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        row = (await db.execute(
            select(Client).where(Client.id == uuid.UUID(client_id))
        )).scalar_one()
    assert row.endereco_json["latitude"] == -23.5613
    assert row.endereco_json["longitude"] == -46.6564


async def test_client_sem_cep_nao_geocodifica_nem_quebra(cenario, monkeypatch):
    async def fail_if_called(cep):
        raise AssertionError("não deveria consultar CEP quando o endereço não tem CEP")
    monkeypatch.setattr(clients_mod, "_consultar_cep_externa", fail_if_called)

    async with AsyncSessionLocal() as db:
        resp = await clients_mod.create_client(
            clients_mod.ClientCreate(
                tipo="PF", nome_completo="Cliente Sem CEP",
                endereco_json={"logradouro": "Rua sem CEP"},
            ),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
        await db.commit()

    assert resp.endereco_json == {"logradouro": "Rua sem CEP"}
