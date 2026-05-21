"""Tests verifying tenant isolation — cross-tenant access must be denied."""
import pytest


async def test_cannot_read_other_tenant_processes(client, tenant_a_headers, tenant_b_process_id):
    """User from tenant A cannot access process belonging to tenant B."""
    res = await client.get(
        f"/api/v1/processes/{tenant_b_process_id}",
        headers=tenant_a_headers,
    )
    assert res.status_code == 404


async def test_cannot_update_other_tenant_process(client, tenant_a_headers, tenant_b_process_id):
    res = await client.put(
        f"/api/v1/processes/{tenant_b_process_id}",
        json={"tribunal": "TJSP"},
        headers=tenant_a_headers,
    )
    assert res.status_code == 404


async def test_cannot_delete_other_tenant_process(client, tenant_a_headers, tenant_b_process_id):
    res = await client.delete(
        f"/api/v1/processes/{tenant_b_process_id}",
        headers=tenant_a_headers,
    )
    assert res.status_code == 404


async def test_list_processes_only_shows_own_tenant(client, tenant_a_headers, tenant_b_process_id):
    """Listing processes only returns results scoped to the authenticated user's tenant."""
    res = await client.get("/api/v1/processes", headers=tenant_a_headers)
    assert res.status_code == 200
    process_ids = [p["id"] for p in res.json()]
    assert tenant_b_process_id not in process_ids


async def test_cannot_read_other_tenant_clients(client, tenant_a_headers, tenant_b_client_id):
    res = await client.get(
        f"/api/v1/clients/{tenant_b_client_id}",
        headers=tenant_a_headers,
    )
    assert res.status_code == 404


async def test_list_clients_only_shows_own_tenant(client, tenant_a_headers, tenant_b_client_id):
    res = await client.get("/api/v1/clients", headers=tenant_a_headers)
    assert res.status_code == 200
    client_ids = [c["id"] for c in res.json()]
    assert tenant_b_client_id not in client_ids
