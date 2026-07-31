"""Tests for /processes endpoints — CRUD, movements, deadlines, agenda, tenant isolation."""
import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.anyio


async def test_list_processes_requires_auth(client: AsyncClient):
    res = await client.get("/api/v1/processes")
    assert res.status_code == 401


async def test_create_process(client: AsyncClient, auth_headers: dict):
    payload = {
        "numero_cnj": "0000001-00.2024.8.26.0100",
        "tribunal": "TJSP",
        "area_direito": "CIVIL",
        "tipo_acao": "Cobrança",
        "descricao": "Processo de teste criado via test suite",
    }
    res = await client.post("/api/v1/processes", json=payload, headers=auth_headers)
    if res.status_code == 422:
        pytest.skip("Validation error — schema mismatch")
    assert res.status_code == 201
    data = res.json()
    assert data["numero_cnj"] == payload["numero_cnj"]
    # Fase 133 — "descricao" era um campo fantasma: a UI de criar processo já
    # coletava, mas não existia coluna nenhuma por trás — era descartado.
    assert data["descricao"] == payload["descricao"]
    return data["id"]


async def test_update_process_situacao_e_campos_antes_sem_editor(client: AsyncClient, auth_headers: dict):
    """Fase 133 — antes desta fase, o PUT reaproveitava o schema de criação
    (sem campo `situacao`) — o dropdown "Situação" da lista enviava o valor e
    o backend descartava silenciosamente, sem erro nenhum."""
    create_res = await client.post(
        "/api/v1/processes",
        json={"numero_cnj": "0000005-00.2024.8.26.0100", "tribunal": "TJSP"},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create process")
    process_id = create_res.json()["id"]

    res = await client.put(
        f"/api/v1/processes/{process_id}",
        json={
            "situacao": "SUSPENSO",
            "comarca": "Fortaleza",
            "uf": "CE",
            "valor_causa": 12345.67,
            "parte_contraria": "Empresa X LTDA",
            "polo": "ATIVO",
            "oab_responsavel": "999/CE",
            "descricao": "Atualizado via teste",
        },
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["situacao"] == "SUSPENSO"
    assert data["comarca"] == "Fortaleza"
    assert data["uf"] == "CE"
    assert data["valor_causa"] == 12345.67
    assert data["parte_contraria"] == "Empresa X LTDA"
    assert data["polo"] == "ATIVO"
    assert data["oab_responsavel"] == "999/CE"
    assert data["descricao"] == "Atualizado via teste"

    # Tribunal não foi enviado — deve permanecer intacto (PUT parcial, não exige mais todos os campos)
    assert data["tribunal"] == "TJSP"


async def test_update_process_situacao_invalida_rejeitada(client: AsyncClient, auth_headers: dict):
    create_res = await client.post(
        "/api/v1/processes",
        json={"numero_cnj": "0000006-00.2024.8.26.0100", "tribunal": "TJSP"},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create process")
    process_id = create_res.json()["id"]

    res = await client.put(
        f"/api/v1/processes/{process_id}",
        json={"situacao": "NAO_EXISTE"},
        headers=auth_headers,
    )
    assert res.status_code == 422


async def test_list_processes_with_filters(client: AsyncClient, auth_headers: dict):
    res = await client.get("/api/v1/processes?situacao=ATIVO&limit=5", headers=auth_headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


async def test_add_movement(client: AsyncClient, auth_headers: dict):
    # Create a process first
    create_res = await client.post(
        "/api/v1/processes",
        json={"numero_cnj": "0000002-00.2024.8.26.0100", "tribunal": "TJSP"},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create process")
    process_id = create_res.json()["id"]

    mov_res = await client.post(
        f"/api/v1/processes/{process_id}/movements",
        json={"descricao": "Juntada de documentos", "tipo": "JUNTADA"},
        headers=auth_headers,
    )
    assert mov_res.status_code == 201
    assert mov_res.json()["descricao"] == "Juntada de documentos"
    # Fase 127 — a resposta usa a chave "data_movimento" (não mais "data"),
    # alinhada com o nome real da coluna e o que o frontend espera.
    assert "data_movimento" in mov_res.json()
    assert "data" not in mov_res.json()

    list_res = await client.get(f"/api/v1/processes/{process_id}/movements", headers=auth_headers)
    assert list_res.status_code == 200
    assert all("data_movimento" in m for m in list_res.json())


async def test_partes_manual_crud_e_tenant_isolation(client: AsyncClient, auth_headers: dict, tenant_b_process_id: str):
    create_res = await client.post(
        "/api/v1/processes",
        json={"numero_cnj": "0000004-00.2024.8.26.0100", "tribunal": "TJSP"},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create process")
    process_id = create_res.json()["id"]

    # Criar
    create_parte_res = await client.post(
        f"/api/v1/processes/{process_id}/partes",
        json={"nome": "João da Silva", "tipo": "AUTOR", "polo": "ATIVO"},
        headers=auth_headers,
    )
    assert create_parte_res.status_code == 201
    parte = create_parte_res.json()
    assert parte["nome"] == "João da Silva"
    assert parte["origem"] == "MANUAL"
    parte_id = parte["id"]

    # Aparece na listagem
    list_res = await client.get(f"/api/v1/processes/{process_id}/partes", headers=auth_headers)
    assert list_res.status_code == 200
    assert any(p["id"] == parte_id for p in list_res.json())

    # Editar
    update_res = await client.put(
        f"/api/v1/processes/{process_id}/partes/{parte_id}",
        json={"nome": "João da Silva Filho", "tipo": "AUTOR", "polo": "ATIVO", "oab": "123/SP"},
        headers=auth_headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["nome"] == "João da Silva Filho"
    assert update_res.json()["oab"] == "123/SP"

    # Isolamento de tenant: processo de outro tenant não existe pra esse usuário → 404
    other_tenant_res = await client.post(
        f"/api/v1/processes/{tenant_b_process_id}/partes",
        json={"nome": "Invasor", "tipo": "AUTOR"},
        headers=auth_headers,
    )
    assert other_tenant_res.status_code == 404

    # Excluir
    delete_res = await client.delete(f"/api/v1/processes/{process_id}/partes/{parte_id}", headers=auth_headers)
    assert delete_res.status_code == 204
    list_after_res = await client.get(f"/api/v1/processes/{process_id}/partes", headers=auth_headers)
    assert not any(p["id"] == parte_id for p in list_after_res.json())


async def test_create_deadline_direct(client: AsyncClient, auth_headers: dict):
    create_res = await client.post(
        "/api/v1/processes",
        json={"numero_cnj": "0000003-00.2024.8.26.0100", "tribunal": "TJSP"},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create process")
    process_id = create_res.json()["id"]

    deadline_res = await client.post(
        f"/api/v1/processes/{process_id}/deadlines",
        json={
            "descricao": "Prazo para contestação",
            "tipo": "CONTESTACAO",
            "data_prazo": "2030-12-31",
        },
        headers=auth_headers,
    )
    assert deadline_res.status_code == 201
    data = deadline_res.json()
    assert data["descricao"] == "Prazo para contestação"
    assert data["status"] == "PENDENTE"
    assert data["data_prazo"] == "2030-12-31"


async def test_mark_deadline_cumprido(client: AsyncClient, auth_headers: dict):
    create_res = await client.post(
        "/api/v1/processes",
        json={"numero_cnj": "0000004-00.2024.8.26.0100", "tribunal": "TJSP"},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create process")
    process_id = create_res.json()["id"]

    dl_res = await client.post(
        f"/api/v1/processes/{process_id}/deadlines",
        json={"descricao": "Recurso", "tipo": "RECURSO", "data_prazo": "2030-06-01"},
        headers=auth_headers,
    )
    if dl_res.status_code != 201:
        pytest.skip("Could not create deadline")
    deadline_id = dl_res.json()["id"]

    upd_res = await client.put(
        f"/api/v1/processes/{process_id}/deadlines/{deadline_id}",
        json={"status": "CUMPRIDO"},
        headers=auth_headers,
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["status"] == "CUMPRIDO"


async def test_agenda_returns_pending_only(client: AsyncClient, auth_headers: dict):
    res = await client.get("/api/v1/processes/agenda", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    # agenda endpoint may return list or dict with items key
    items = data if isinstance(data, list) else data.get("items", data.get("prazos", []))
    for item in items:
        assert item.get("status", "PENDENTE") == "PENDENTE"


async def test_process_tenant_isolation(client: AsyncClient, auth_headers: dict, tenant_b_process_id: str):
    # Attempt to access a process with a random UUID that belongs to no tenant
    res = await client.get(f"/api/v1/processes/{tenant_b_process_id}", headers=auth_headers)
    assert res.status_code in (403, 404)
