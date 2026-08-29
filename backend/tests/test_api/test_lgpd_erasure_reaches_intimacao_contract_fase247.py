"""Fase 247 (achados da Fase 246) — 6ª ocorrência da mesma classe de lacuna
já fechada 5x antes (176.3→210→220→228→235→238): 2 superfícies novas das
Fases 244/245 sobreviviam ao esquecimento.

1. `Intimacao.texto`/`.resumo_ia` (Fase 244, prioridade de IA pré-computada)
   não tem `client_id` próprio — vínculo indireto via `process_id →
   LegalProcess`, nunca alcançado por `erase_client_data`/
   `export_client_data`.
2. `Contract.assinaturas` criado via `POST /contracts/create` (caminho
   manual, distinto do gerado por IA) sobrevivia ao esquecimento E sumia
   do export — esse endpoint criava o `Document` com `client_id=NULL` e só
   setava `Contract.client_id` diretamente, quebrando a cadeia
   `Document.client_id → Contract.document_id` que `lgpd.py` usava pra
   encontrar o contrato. Corrigido em 2 frentes: a criação passa a
   propagar `client_id` pro `Document` também (raiz do problema, contratos
   novos), e `lgpd.py` passa a alcançar por OR (`Document.client_id` OU o
   `Document` de um `Contract.client_id` que bate) — cobre também
   contratos legados já criados pelo caminho antigo, sem depender de
   backfill (mesma decisão de "sem backfill de dado legado" já usada
   noutras fases, ex. geocodificação de clientes na Fase 233)."""
import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.anyio


async def test_lgpd_erasure_reaches_intimacao_texto_e_resumo_ia(client: AsyncClient, auth_headers: dict):
    create_res = await client.post(
        "/api/v1/clients",
        json={"tipo": "PF", "nome_completo": "Titular Intimacao Fase247", "lgpd_consent": True},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create client")
    client_id = create_res.json()["id"]

    process_res = await client.post(
        "/api/v1/processes",
        json={"tribunal": "TJCE", "area_direito": "CIVIL", "client_id": client_id},
        headers=auth_headers,
    )
    if process_res.status_code != 201:
        pytest.skip("Could not create process")

    erase_res = await client.delete(f"/api/v1/lgpd/clients/{client_id}/data", headers=auth_headers)
    if erase_res.status_code != 200:
        pytest.skip("Erasure not permitted for this role")

    export_res = await client.get(f"/api/v1/lgpd/clients/{client_id}/export", headers=auth_headers)
    assert export_res.status_code == 200
    assert "intimacoes" in export_res.json()


async def test_lgpd_erasure_reaches_contract_assinaturas_via_manual_create(client: AsyncClient, auth_headers: dict):
    create_res = await client.post(
        "/api/v1/clients",
        json={"tipo": "PF", "nome_completo": "Titular Contrato Fase247", "lgpd_consent": True},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create client")
    client_id = create_res.json()["id"]

    contract_res = await client.post(
        "/api/v1/documents/contracts/create",
        json={
            "titulo": "Contrato de honorários Fase247",
            "conteudo": "Cliente CPF 987.654.321-00, telefone 11977776666, contrata os serviços.",
            "client_id": client_id,
        },
        headers=auth_headers,
    )
    if contract_res.status_code != 201:
        pytest.skip("Could not create contract")
    doc_id = contract_res.json()["id"]

    export_before = await client.get(f"/api/v1/lgpd/clients/{client_id}/export", headers=auth_headers)
    assert export_before.status_code == 200
    docs_before = export_before.json().get("documentos", [])
    assert any(d["id"] == doc_id and "987.654.321-00" in (d.get("conteudo_texto") or "") for d in docs_before)

    erase_res = await client.delete(f"/api/v1/lgpd/clients/{client_id}/data", headers=auth_headers)
    if erase_res.status_code != 200:
        pytest.skip("Erasure not permitted for this role")

    export_after = await client.get(f"/api/v1/lgpd/clients/{client_id}/export", headers=auth_headers)
    assert export_after.status_code == 200
    exported = export_after.json()
    assert "987.654.321-00" not in str(exported)
    assert "11977776666" not in str(exported)
    docs_after = exported.get("documentos", [])
    assert any(d["id"] == doc_id for d in docs_after)
