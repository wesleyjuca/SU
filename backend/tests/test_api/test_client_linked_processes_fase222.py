"""Fase 222 — usuário reportou (com screenshots) que a Cliente 360 mostrava
"Processos Vinculados (0)" pra um cliente que um processo real já listava
como parte vinculada. Confirmado que `LegalProcess.client_id` (usado por
`GET /processes?client_id=`) e `ProcessParty.client_id` (Fase 179, setado
ao vincular manualmente uma parte a um cliente existente) são 2 FKs
independentes, nunca sincronizadas — comum em processo importado por OAB
(`fonte="OAB"`), que nunca popula `LegalProcess.client_id`. Fix:
`client_linked_processes_filter()` (`app/models/process.py`) passa a
cobrir os 2 caminhos, reaproveitado em `GET /processes`, `client_health_
score`, `client_timeline`, `client_dossie_pdf` e nos 3 endpoints de
`/portal`."""
import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.anyio


async def _criar_cliente(client: AsyncClient, auth_headers: dict, nome: str) -> str:
    res = await client.post(
        "/api/v1/clients",
        json={"tipo": "PF", "nome_completo": nome, "lgpd_consent": True},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


async def _criar_processo_sem_client_id(client: AsyncClient, auth_headers: dict, numero_cnj: str) -> str:
    """Imita o caminho de importação por OAB (`oab_capture.py`), que nunca
    seta `LegalProcess.client_id`."""
    res = await client.post(
        "/api/v1/processes",
        json={"numero_cnj": numero_cnj, "tribunal": "TJAC"},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


async def test_processo_alcancavel_so_via_parte_aparece_vinculado(client: AsyncClient, auth_headers: dict):
    client_id = await _criar_cliente(client, auth_headers, "Titular Fase222 Reproducao")
    process_id = await _criar_processo_sem_client_id(client, auth_headers, "5008963-31.2026.8.01.0001")

    antes = await client.get(f"/api/v1/processes?client_id={client_id}", headers=auth_headers)
    assert antes.status_code == 200
    assert antes.json() == []  # reproduz o bug relatado: 0 processos vinculados

    parte_res = await client.post(
        f"/api/v1/processes/{process_id}/partes",
        json={"tipo": "REU", "nome": "Titular Fase222 Reproducao", "client_id": client_id},
        headers=auth_headers,
    )
    assert parte_res.status_code == 201, parte_res.text

    depois = await client.get(f"/api/v1/processes?client_id={client_id}", headers=auth_headers)
    assert depois.status_code == 200
    ids = [p["id"] for p in depois.json()]
    assert process_id in ids


async def test_processo_com_client_id_direto_continua_aparecendo(client: AsyncClient, auth_headers: dict):
    client_id = await _criar_cliente(client, auth_headers, "Titular Fase222 Regressao")
    res = await client.post(
        "/api/v1/processes",
        json={"numero_cnj": "2222222-22.2026.8.01.0001", "tribunal": "TJAC", "client_id": client_id},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    process_id = res.json()["id"]

    lista = await client.get(f"/api/v1/processes?client_id={client_id}", headers=auth_headers)
    assert lista.status_code == 200
    ids = [p["id"] for p in lista.json()]
    assert process_id in ids


async def test_duas_partes_mesmo_cliente_nao_duplica_processo(client: AsyncClient, auth_headers: dict):
    client_id = await _criar_cliente(client, auth_headers, "Titular Fase222 Dedup")
    process_id = await _criar_processo_sem_client_id(client, auth_headers, "3333333-33.2026.8.01.0001")

    for tipo, nome in (("REU", "Parte A"), ("AUTOR", "Parte B")):
        r = await client.post(
            f"/api/v1/processes/{process_id}/partes",
            json={"tipo": tipo, "nome": nome, "client_id": client_id},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text

    lista = await client.get(f"/api/v1/processes?client_id={client_id}", headers=auth_headers)
    assert lista.status_code == 200
    ocorrencias = [p["id"] for p in lista.json() if p["id"] == process_id]
    assert len(ocorrencias) == 1


async def test_processo_via_parte_conta_no_health_score_e_timeline(client: AsyncClient, auth_headers: dict):
    client_id = await _criar_cliente(client, auth_headers, "Titular Fase222 HealthTimeline")
    process_id = await _criar_processo_sem_client_id(client, auth_headers, "4444444-44.2026.8.01.0001")
    r = await client.post(
        f"/api/v1/processes/{process_id}/partes",
        json={"tipo": "REU", "nome": "Titular Fase222 HealthTimeline", "client_id": client_id},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text

    timeline = await client.get(f"/api/v1/clients/{client_id}/timeline", headers=auth_headers)
    assert timeline.status_code == 200
    assert any(e["tipo"] == "processo" and e["subtipo"] == "aberto" for e in timeline.json())

    health = await client.get(f"/api/v1/clients/{client_id}/health-score", headers=auth_headers)
    assert health.status_code == 200
