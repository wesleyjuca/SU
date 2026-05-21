"""Tests for financial CRUD endpoints."""
import pytest


async def test_create_financial_entry(client, auth_headers):
    res = await client.post("/api/v1/financial", json={
        "tipo": "RECEITA",
        "categoria": "HONORARIOS",
        "descricao": "Honorários contrato X",
        "valor": 5000.00,
        "status": "PENDENTE",
    }, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["tipo"] == "RECEITA"
    assert data["valor"] == 5000.00


async def test_list_financial_entries(client, auth_headers):
    res = await client.get("/api/v1/financial", headers=auth_headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


async def test_update_financial_entry(client, auth_headers):
    create_res = await client.post("/api/v1/financial", json={
        "tipo": "DESPESA",
        "descricao": "Custas processuais",
        "valor": 300.00,
    }, headers=auth_headers)
    assert create_res.status_code == 201
    entry_id = create_res.json()["id"]
    update_res = await client.put(f"/api/v1/financial/{entry_id}", json={
        "descricao": "Custas processuais atualizadas",
        "valor": 350.00,
    }, headers=auth_headers)
    assert update_res.status_code == 200
    assert update_res.json()["valor"] == 350.00


async def test_mark_paid(client, auth_headers):
    create_res = await client.post("/api/v1/financial", json={
        "tipo": "RECEITA",
        "descricao": "Honorário mensal",
        "valor": 2000.00,
        "status": "PENDENTE",
    }, headers=auth_headers)
    entry_id = create_res.json()["id"]
    res = await client.post(f"/api/v1/financial/{entry_id}/mark-paid", headers=auth_headers)
    assert res.status_code == 200


async def test_delete_financial_entry(client, auth_headers):
    create_res = await client.post("/api/v1/financial", json={
        "tipo": "DESPESA",
        "descricao": "A remover",
        "valor": 100.00,
    }, headers=auth_headers)
    entry_id = create_res.json()["id"]
    del_res = await client.delete(f"/api/v1/financial/{entry_id}", headers=auth_headers)
    assert del_res.status_code == 204
    list_res = await client.get("/api/v1/financial", headers=auth_headers)
    ids = [e["id"] for e in list_res.json()]
    assert entry_id not in ids


async def test_unauthenticated_financial_denied(client):
    res = await client.get("/api/v1/financial")
    assert res.status_code == 401
