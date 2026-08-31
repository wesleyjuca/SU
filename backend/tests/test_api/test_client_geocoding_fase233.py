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


# ─── Fase 253 — causa-raiz do marcador de cliente em local incompatível ─────
# Achado: `_geocodificar_endereco` só olhava se o payload JÁ tinha lat/lng
# pra decidir se pulava a geocodificação, nunca comparava com o CEP
# anterior. O formulário de edição reidrata o endereço inteiro (inclusive
# lat/lng antigas), então trocar só o CEP salvava o endereço novo com a
# coordenada do CEP ANTIGO grudada. Os testes abaixo provam o
# COMPORTAMENTO CORRETO pós-fix — não reproduzem o bug em si (exigiria
# reverter o código), provam que a causa-raiz está de fato fechada.

_COORDS_POR_CEP = {
    "01310100": {"logradouro": "Av. Paulista", "bairro": "Bela Vista", "cidade": "São Paulo", "uf": "SP",
                 "latitude": -23.5613, "longitude": -46.6564},
    "69900000": {"logradouro": "Rua Rui Barbosa", "bairro": "Centro", "cidade": "Rio Branco", "uf": "AC",
                 "latitude": -9.9750, "longitude": -67.8100},
}


def _fake_consultar_cep_por_cep(contador: dict | None = None):
    async def fake(cep):
        if contador is not None:
            contador["n"] = contador.get("n", 0) + 1
        numero = "".join(ch for ch in cep if ch.isdigit())
        return _COORDS_POR_CEP.get(numero)
    return fake


async def test_editar_cep_atualiza_coordenada_nao_fica_presa_ao_cep_antigo(cenario, monkeypatch):
    """Reprodução do cenário exato do achado: cliente geocodificado pro
    CEP de São Paulo, depois editado pro CEP de Rio Branco/AC — a
    coordenada persistida tem que ser a de Rio Branco, não a antiga de
    São Paulo grudada."""
    monkeypatch.setattr(clients_mod, "_consultar_cep_externa", _fake_consultar_cep_por_cep())
    async with AsyncSessionLocal() as db:
        created = await clients_mod.create_client(
            clients_mod.ClientCreate(
                tipo="PF", nome_completo="Cliente Fase253",
                endereco_json={"cep": "01310-100", "logradouro": "", "bairro": "", "cidade": "", "uf": ""},
            ),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
        await db.commit()
        client_id = created.id
    assert created.endereco_json["latitude"] == -23.5613  # confirma que nasceu com a coordenada de SP

    async with AsyncSessionLocal() as db:
        # Simula exatamente o payload que o frontend manda hoje: endereço
        # novo (CEP de Rio Branco) + latitude/longitude ANTIGAS (de SP),
        # porque `abrirEdicao` reidrata o endereco_json inteiro do cliente.
        updated = await clients_mod.update_client(
            client_id,
            clients_mod.ClientCreate(
                tipo="PF", nome_completo="Cliente Fase253",
                endereco_json={
                    "cep": "69900-000", "logradouro": "", "bairro": "", "cidade": "", "uf": "",
                    "latitude": -23.5613, "longitude": -46.6564,
                },
            ),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
        await db.commit()

    assert updated.endereco_json["latitude"] == -9.9750
    assert updated.endereco_json["longitude"] == -67.8100
    assert updated.endereco_json["geocode_source"] == "brasilapi"
    assert "geocoded_at" in updated.endereco_json

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        row = (await db.execute(select(Client).where(Client.id == uuid.UUID(client_id)))).scalar_one()
    assert row.endereco_json["latitude"] == -9.9750
    assert row.endereco_json["longitude"] == -67.8100


async def test_editar_sem_mudar_cep_nao_rebate_a_api(cenario, monkeypatch):
    """CEP não mudou — não deve reconsultar a BrasilAPI de novo (evita
    reconsulta desnecessária, comportamento já existente preservado)."""
    contador: dict = {}
    monkeypatch.setattr(clients_mod, "_consultar_cep_externa", _fake_consultar_cep_por_cep(contador))
    async with AsyncSessionLocal() as db:
        created = await clients_mod.create_client(
            clients_mod.ClientCreate(
                tipo="PF", nome_completo="Cliente Fase253b",
                endereco_json={"cep": "01310-100", "logradouro": "", "bairro": "", "cidade": "", "uf": ""},
            ),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
        await db.commit()
        client_id = created.id
    assert contador["n"] == 1

    async with AsyncSessionLocal() as db:
        updated = await clients_mod.update_client(
            client_id,
            clients_mod.ClientCreate(
                tipo="PF", nome_completo="Cliente Fase253b — nome mudou, endereço não",
                endereco_json={
                    "cep": "01310-100", "logradouro": "Av. Paulista", "bairro": "Bela Vista",
                    "cidade": "São Paulo", "uf": "SP", "latitude": -23.5613, "longitude": -46.6564,
                },
            ),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
        await db.commit()

    assert contador["n"] == 1  # não rebateu a API — mesmo CEP de antes
    assert updated.endereco_json["latitude"] == -23.5613


async def test_cep_mudou_mas_geocodificacao_falha_zera_coordenada_antiga(cenario, monkeypatch):
    """CEP mudou pra um que a fonte não consegue geocodificar (simulando
    BrasilAPI fora do ar/CEP sem coordenada conhecida) — a coordenada
    antiga não pode ficar silenciosamente associada ao endereço novo."""
    monkeypatch.setattr(clients_mod, "_consultar_cep_externa", _fake_consultar_cep_por_cep())
    async with AsyncSessionLocal() as db:
        created = await clients_mod.create_client(
            clients_mod.ClientCreate(
                tipo="PF", nome_completo="Cliente Fase253c",
                endereco_json={"cep": "01310-100", "logradouro": "", "bairro": "", "cidade": "", "uf": ""},
            ),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
        await db.commit()
        client_id = created.id

    async with AsyncSessionLocal() as db:
        updated = await clients_mod.update_client(
            client_id,
            clients_mod.ClientCreate(
                tipo="PF", nome_completo="Cliente Fase253c",
                endereco_json={
                    "cep": "99999-999", "logradouro": "", "bairro": "", "cidade": "", "uf": "",
                    "latitude": -23.5613, "longitude": -46.6564,
                },
            ),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
        await db.commit()

    assert updated.endereco_json["latitude"] is None
    assert updated.endereco_json["longitude"] is None
    assert "geocode_source" not in updated.endereco_json


async def test_recalcular_localizacao_forca_nova_consulta(cenario, monkeypatch):
    """Botão "Recalcular localização" — re-consulta mesmo sem o CEP ter
    mudado (útil pra registros REQUER_REVISAO herdados de antes do fix,
    ou que ficaram sem coordenada por falha temporária)."""
    contador: dict = {}
    monkeypatch.setattr(clients_mod, "_consultar_cep_externa", _fake_consultar_cep_por_cep(contador))
    async with AsyncSessionLocal() as db:
        created = await clients_mod.create_client(
            clients_mod.ClientCreate(
                tipo="PF", nome_completo="Cliente Fase253d",
                endereco_json={"cep": "01310-100", "logradouro": "", "bairro": "", "cidade": "", "uf": ""},
            ),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
        await db.commit()
        client_id = created.id
    assert contador["n"] == 1

    async with AsyncSessionLocal() as db:
        resp = await clients_mod.recalcular_localizacao(
            client_id, current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
        await db.commit()

    assert contador["n"] == 2  # rebateu a API mesmo sem o CEP mudar
    assert resp.endereco_json["latitude"] == -23.5613
    assert resp.endereco_json["geocode_source"] == "brasilapi"


async def test_auditoria_geolocalizacao_classifica_status(cenario, monkeypatch):
    """GET /clients/geolocalizacao/auditoria — só relatório, classifica
    cada cliente com CEP em NAO_GEOCODIFICADO/REQUER_REVISAO/VALIDADA."""
    monkeypatch.setattr(clients_mod, "_consultar_cep_externa", _fake_consultar_cep_por_cep())
    async with AsyncSessionLocal() as db:
        # VALIDADA — passa pelo fluxo normal de criação (geocode_source setado).
        await clients_mod.create_client(
            clients_mod.ClientCreate(
                tipo="PF", nome_completo="Cliente Validado",
                endereco_json={"cep": "01310-100", "logradouro": "", "bairro": "", "cidade": "", "uf": ""},
            ),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
        # NAO_GEOCODIFICADO — CEP que a fonte não resolve.
        await clients_mod.create_client(
            clients_mod.ClientCreate(
                tipo="PF", nome_completo="Cliente Sem Coordenada",
                endereco_json={"cep": "88888-888", "logradouro": "", "bairro": "", "cidade": "", "uf": ""},
            ),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
        await db.commit()
        # REQUER_REVISAO — simula dado legado (de antes do fix), inserido
        # direto no banco sem passar por `_geocodificar_endereco` (mesma
        # forma como um registro pré-Fase-253 ficaria: tem coordenada, mas
        # nunca teve `geocode_source`).
        legado = Client(
            tenant_id=cenario["tenant"], responsavel_id=cenario["user"], tipo="PF",
            nome_completo="Cliente Legado",
            endereco_json={"cep": "01310-100", "latitude": -23.55, "longitude": -46.63},
        )
        db.add(legado)
        await db.commit()

    async with AsyncSessionLocal() as db:
        resultado = await clients_mod.auditoria_geolocalizacao(
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )

    assert resultado["total"] == 3
    assert resultado["contagem"] == {"NAO_GEOCODIFICADO": 1, "REQUER_REVISAO": 1, "VALIDADA": 1}
    status_por_nome = {c["nome"]: c["status"] for c in resultado["clientes"]}
    assert status_por_nome["Cliente Validado"] == "VALIDADA"
    assert status_por_nome["Cliente Sem Coordenada"] == "NAO_GEOCODIFICADO"
    assert status_por_nome["Cliente Legado"] == "REQUER_REVISAO"


# ─── Fase 254 — ajuste manual (arrastar marcador no mapa) ───────────────────

async def test_ajustar_localizacao_manual_persiste_com_geocode_source_manual(cenario):
    async with AsyncSessionLocal() as db:
        legado = Client(
            tenant_id=cenario["tenant"], responsavel_id=cenario["user"], tipo="PF",
            nome_completo="Cliente Pra Ajustar",
            endereco_json={"cep": "01310-100", "latitude": -23.55, "longitude": -46.63},
        )
        db.add(legado)
        await db.commit()
        client_id = legado.id

    async with AsyncSessionLocal() as db:
        resp = await clients_mod.ajustar_localizacao_manual(
            str(client_id),
            clients_mod.LocalizacaoManualBody(latitude=-9.9750, longitude=-67.8100),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
        await db.commit()

    assert resp.endereco_json["latitude"] == -9.9750
    assert resp.endereco_json["longitude"] == -67.8100
    assert resp.endereco_json["geocode_source"] == "manual"
    assert "geocoded_at" in resp.endereco_json
    # CEP/demais campos do endereço preservados — só a coordenada muda.
    assert resp.endereco_json["cep"] == "01310-100"

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        row = (await db.execute(select(Client).where(Client.id == client_id))).scalar_one()
    assert row.endereco_json["latitude"] == -9.9750
    assert row.endereco_json["geocode_source"] == "manual"


async def test_ajustar_localizacao_manual_rejeita_coordenada_fora_de_faixa(cenario):
    async with AsyncSessionLocal() as db:
        cliente = Client(
            tenant_id=cenario["tenant"], responsavel_id=cenario["user"], tipo="PF",
            nome_completo="Cliente Coordenada Invalida",
            endereco_json={"cep": "01310-100"},
        )
        db.add(cliente)
        await db.commit()
        client_id = cliente.id

    from fastapi import HTTPException
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await clients_mod.ajustar_localizacao_manual(
                str(client_id),
                clients_mod.LocalizacaoManualBody(latitude=999.0, longitude=-46.63),
                current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
            )
    assert exc.value.status_code == 422

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        row = (await db.execute(select(Client).where(Client.id == client_id))).scalar_one()
    assert row.endereco_json.get("latitude") is None  # não gravou a coordenada inválida


async def test_ajustar_localizacao_manual_cliente_de_outro_tenant_404(cenario):
    async with AsyncSessionLocal() as db:
        outro_tenant = Tenant(name="Outro Tenant 254", slug=f"outro-254-{uuid.uuid4().hex[:8]}")
        db.add(outro_tenant)
        await db.flush()
        cliente_outro = Client(
            tenant_id=outro_tenant.id, tipo="PF", nome_completo="Cliente de Outro Tenant",
            endereco_json={"cep": "01310-100"},
        )
        db.add(cliente_outro)
        await db.commit()
        client_id = cliente_outro.id
        outro_tenant_id = outro_tenant.id

    from app.core.exceptions import NotFoundError
    async with AsyncSessionLocal() as db:
        with pytest.raises(NotFoundError):
            await clients_mod.ajustar_localizacao_manual(
                str(client_id),
                clients_mod.LocalizacaoManualBody(latitude=-9.9750, longitude=-67.8100),
                current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
            )

    async with AsyncSessionLocal() as db:
        await db.execute(Client.__table__.delete().where(Client.tenant_id == outro_tenant_id))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == outro_tenant_id))
        await db.commit()


# --- Fase 255: correção em massa de geolocalização (POST
# /clients/geolocalizacao/recalcular-lote), único item que sobrou do
# backlog de mapa das Fases 253/254 ("correção em massa com confirmação
# explícita"). ---

async def test_recalcular_lote_processa_ok_sem_cep_e_exclui_outro_tenant(cenario, monkeypatch):
    monkeypatch.setattr(clients_mod, "_consultar_cep_externa", _fake_consultar_cep_por_cep())

    async with AsyncSessionLocal() as db:
        cliente_ok = Client(
            tenant_id=cenario["tenant"], responsavel_id=cenario["user"], tipo="PF",
            nome_completo="Lote OK", endereco_json={"cep": "01310-100"},
        )
        cliente_sem_cep = Client(
            tenant_id=cenario["tenant"], responsavel_id=cenario["user"], tipo="PF",
            nome_completo="Lote Sem CEP", endereco_json={"cidade": "SP"},
        )
        outro_tenant = Tenant(name="Outro Tenant 255", slug=f"outro-255-{uuid.uuid4().hex[:8]}")
        db.add_all([cliente_ok, cliente_sem_cep, outro_tenant])
        await db.flush()
        cliente_outro = Client(
            tenant_id=outro_tenant.id, tipo="PF", nome_completo="Cliente de Outro Tenant",
            endereco_json={"cep": "01310-200"},
        )
        db.add(cliente_outro)
        await db.commit()
        id_ok, id_sem_cep, id_outro = cliente_ok.id, cliente_sem_cep.id, cliente_outro.id
        outro_tenant_id = outro_tenant.id

    async with AsyncSessionLocal() as db:
        resp = await clients_mod.recalcular_localizacao_lote(
            clients_mod.RecalcularLoteBody(client_ids=[str(id_ok), str(id_sem_cep), str(id_outro)]),
            current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
        )
        await db.commit()

    assert resp["solicitados"] == 3
    por_id = {p["id"]: p["status"] for p in resp["processados"]}
    assert por_id[str(id_ok)] == "ok"
    assert por_id[str(id_sem_cep)] == "sem_cep"
    assert por_id[str(id_outro)] == "nao_encontrado"

    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(Client).where(Client.id == id_ok))).scalar_one()
    assert row.endereco_json["latitude"] is not None
    assert row.endereco_json["geocode_source"] == "brasilapi"

    async with AsyncSessionLocal() as db:
        await db.execute(Client.__table__.delete().where(Client.tenant_id == outro_tenant_id))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == outro_tenant_id))
        await db.commit()


async def test_recalcular_lote_rejeita_vazio_e_acima_do_teto(cenario):
    from fastapi import HTTPException

    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await clients_mod.recalcular_localizacao_lote(
                clients_mod.RecalcularLoteBody(client_ids=[]),
                current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
            )
    assert exc.value.status_code == 422

    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await clients_mod.recalcular_localizacao_lote(
                clients_mod.RecalcularLoteBody(client_ids=[str(uuid.uuid4()) for _ in range(201)]),
                current_user=_CurrentUser(cenario["tenant"], cenario["user"]), db=db,
            )
    assert exc.value.status_code == 422
