"""Fase 257 — evolução do mapa (a pedido do usuário, "evolua o mapa,
verifique se é mais viável usar google maps"). Teste de regressão pros 4
pontos implementados: (1) `GET /clients/{id}/mapa-resumo` (score + processos
ativos + próximo prazo, popup do mapa); (2) `GET /clients/geolocalizacao/
regioes` (agregação por cidade/UF, aba "Geográfico" em Relatórios);
(3) `_geocodificar_endereco` tenta Nominatim primeiro quando `numero` está
presente (precisão de endereço exato), com fallback fail-soft pra
BrasilAPI; (4) distância do escritório é cálculo puro client-side, sem
endpoint novo (não testado aqui — sem superfície de backend). Mesmo padrão
Postgres real + monkeypatch de chamada externa já usado desde a Fase 217/233."""
import uuid
from datetime import date, timedelta

import pytest

import app.api.v1.clients as clients_mod
from app.db.base import AsyncSessionLocal
from app.models.client import Client
from app.models.process import LegalProcess, ProcessDeadline
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.anyio


class _CurrentUser:
    def __init__(self, tenant_id, uid=None, role="ADMIN"):
        self.tenant_id = tenant_id
        self.id = uid or uuid.uuid4()
        self.role = role


@pytest.fixture
async def cenario():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 257", slug=f"teste-257-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        user = User(
            email=f"user-257-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Usuario Teste 257", role="ADMIN", tenant_id=tenant.id,
        )
        db.add(user)
        await db.commit()
        ids = {"tenant": tenant.id, "user": user.id}
    yield ids
    async with AsyncSessionLocal() as db:
        proc_ids = (await db.execute(
            __import__("sqlalchemy").select(LegalProcess.id).where(LegalProcess.tenant_id == ids["tenant"])
        )).scalars().all()
        if proc_ids:
            await db.execute(ProcessDeadline.__table__.delete().where(ProcessDeadline.process_id.in_(proc_ids)))
        await db.execute(LegalProcess.__table__.delete().where(LegalProcess.tenant_id == ids["tenant"]))
        await db.execute(Client.__table__.delete().where(Client.tenant_id == ids["tenant"]))
        await db.execute(User.__table__.delete().where(User.id == ids["user"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == ids["tenant"]))
        await db.commit()


async def test_mapa_resumo_processos_ativos_e_proximo_prazo(cenario):
    async with AsyncSessionLocal() as db:
        cliente = Client(
            tenant_id=cenario["tenant"], tipo="PF", nome_completo="Cliente Mapa 257", status="ATIVO",
        )
        db.add(cliente)
        await db.flush()
        processo = LegalProcess(
            tenant_id=cenario["tenant"], client_id=cliente.id, numero_cnj="1111111-11.2026.8.26.0100",
            tribunal="TJSP", area_direito="CIVEL", situacao="ATIVO",
        )
        db.add(processo)
        await db.flush()
        prazo = ProcessDeadline(
            process_id=processo.id, descricao="Réplica", tipo="PRAZO", status="PENDENTE",
            data_prazo=date.today() + timedelta(days=3),
        )
        db.add(prazo)
        await db.commit()
        cliente_id = cliente.id

    cu = _CurrentUser(cenario["tenant"], cenario["user"])
    async with AsyncSessionLocal() as db:
        resumo = await clients_mod.client_mapa_resumo(str(cliente_id), current_user=cu, db=db)

    assert resumo["processos_ativos"] == 1
    assert resumo["proximo_prazo"]["descricao"] == "Réplica"
    assert 0 <= resumo["score"] <= 100
    assert resumo["banda"] in ("saudavel", "atencao", "risco")


async def test_mapa_resumo_cross_tenant_nao_encontrado(cenario):
    async with AsyncSessionLocal() as db:
        outro = Tenant(name="Outro 257", slug=f"outro-257-{uuid.uuid4().hex[:8]}")
        db.add(outro)
        await db.commit()
        outro_id = outro.id

    async with AsyncSessionLocal() as db:
        cliente = Client(tenant_id=cenario["tenant"], tipo="PF", nome_completo="Cliente A", status="ATIVO")
        db.add(cliente)
        await db.commit()
        cliente_id = cliente.id

    cu_outro = _CurrentUser(outro_id)
    with pytest.raises(Exception) as exc_info:
        async with AsyncSessionLocal() as db:
            await clients_mod.client_mapa_resumo(str(cliente_id), current_user=cu_outro, db=db)
    assert "NotFoundError" in type(exc_info.value).__name__ or "404" in str(exc_info.value)

    async with AsyncSessionLocal() as db:
        await db.execute(Tenant.__table__.delete().where(Tenant.id == outro_id))
        await db.commit()


async def test_regioes_geolocalizacao_agrega_por_cidade_uf(cenario):
    async with AsyncSessionLocal() as db:
        db.add_all([
            Client(tenant_id=cenario["tenant"], tipo="PF", nome_completo="C1", status="ATIVO",
                   endereco_json={"cep": "01310-100", "cidade": "São Paulo", "uf": "SP",
                                  "latitude": -23.5, "longitude": -46.6, "geocode_source": "brasilapi"}),
            Client(tenant_id=cenario["tenant"], tipo="PF", nome_completo="C2", status="ATIVO",
                   endereco_json={"cep": "01310-100", "cidade": "São Paulo", "uf": "SP",
                                  "latitude": -23.5, "longitude": -46.6, "geocode_source": "brasilapi"}),
            Client(tenant_id=cenario["tenant"], tipo="PF", nome_completo="C3", status="ATIVO",
                   endereco_json={"cep": "20040-020", "cidade": "Rio de Janeiro", "uf": "RJ",
                                  "latitude": -22.9, "longitude": -43.1, "geocode_source": "brasilapi"}),
            # não geocodificado — não deve entrar na agregação
            Client(tenant_id=cenario["tenant"], tipo="PF", nome_completo="C4", status="ATIVO",
                   endereco_json={"cep": "99999-999"}),
        ])
        await db.commit()

    cu = _CurrentUser(cenario["tenant"], cenario["user"])
    async with AsyncSessionLocal() as db:
        regioes = await clients_mod.regioes_geolocalizacao(current_user=cu, db=db)

    assert regioes["total_geocodificados"] == 3
    mapa = {(r["cidade"], r["uf"]): r["quantidade"] for r in regioes["regioes"]}
    assert mapa[("São Paulo", "SP")] == 2
    assert mapa[("Rio de Janeiro", "RJ")] == 1


async def test_geocodificar_endereco_prioriza_nominatim_quando_numero_presente(monkeypatch):
    chamadas = {"nominatim": 0, "brasilapi": 0}

    async def _fake_nominatim(logradouro, numero, cidade, uf):
        chamadas["nominatim"] += 1
        return (-23.5613, -46.6565)

    async def _fake_brasilapi(cep):
        chamadas["brasilapi"] += 1
        return {"logradouro": "X", "bairro": "Y", "cidade": "Z", "uf": "SP",
                "latitude": -23.55, "longitude": -46.63}

    monkeypatch.setattr(clients_mod, "_geocodificar_nominatim", _fake_nominatim)
    monkeypatch.setattr(clients_mod, "_consultar_cep_externa", _fake_brasilapi)

    endereco = {"cep": "01310-100", "logradouro": "Avenida Paulista", "numero": "1000",
                "bairro": "Bela Vista", "cidade": "São Paulo", "uf": "SP"}
    resultado = await clients_mod._geocodificar_endereco(endereco, None)

    assert chamadas["nominatim"] == 1
    assert chamadas["brasilapi"] == 0
    assert resultado["geocode_source"] == "nominatim"
    assert resultado["latitude"] == -23.5613


async def test_geocodificar_endereco_sem_numero_usa_so_brasilapi(monkeypatch):
    chamadas = {"nominatim": 0, "brasilapi": 0}

    async def _fake_nominatim(logradouro, numero, cidade, uf):
        chamadas["nominatim"] += 1
        return (-23.5613, -46.6565)

    async def _fake_brasilapi(cep):
        chamadas["brasilapi"] += 1
        return {"logradouro": "X", "bairro": "Y", "cidade": "Z", "uf": "SP",
                "latitude": -23.55, "longitude": -46.63}

    monkeypatch.setattr(clients_mod, "_geocodificar_nominatim", _fake_nominatim)
    monkeypatch.setattr(clients_mod, "_consultar_cep_externa", _fake_brasilapi)

    endereco = {"cep": "20040-020", "logradouro": "Rua do Ouvidor", "bairro": "Centro",
                "cidade": "Rio de Janeiro", "uf": "RJ"}
    resultado = await clients_mod._geocodificar_endereco(endereco, None)

    assert chamadas["nominatim"] == 0
    assert chamadas["brasilapi"] == 1
    assert resultado["geocode_source"] == "brasilapi"


async def test_geocodificar_endereco_nominatim_falha_cai_pra_brasilapi(monkeypatch):
    chamadas = {"nominatim": 0, "brasilapi": 0}

    async def _fake_nominatim_falha(logradouro, numero, cidade, uf):
        chamadas["nominatim"] += 1
        return None

    async def _fake_brasilapi(cep):
        chamadas["brasilapi"] += 1
        return {"logradouro": "X", "bairro": "Y", "cidade": "Z", "uf": "SP",
                "latitude": -23.55, "longitude": -46.63}

    monkeypatch.setattr(clients_mod, "_geocodificar_nominatim", _fake_nominatim_falha)
    monkeypatch.setattr(clients_mod, "_consultar_cep_externa", _fake_brasilapi)

    endereco = {"cep": "01310-100", "logradouro": "Avenida Paulista", "numero": "999999",
                "bairro": "Bela Vista", "cidade": "São Paulo", "uf": "SP"}
    resultado = await clients_mod._geocodificar_endereco(endereco, None)

    assert chamadas["nominatim"] == 1
    assert chamadas["brasilapi"] == 1
    assert resultado["geocode_source"] == "brasilapi"
