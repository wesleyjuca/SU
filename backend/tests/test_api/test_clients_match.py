"""Fase 181 — GET /clients/match: vínculo automático de cliente por CPF/CNPJ
exato no cadastro manual de parte de processo, com sugestão por nome quando
não há CPF/CNPJ batendo. Client.cpf/cnpj são cifrados em repouso (Fase 149,
Fernet) — o teste confirma que o match funciona mesmo com máscara diferente
da que foi usada ao cadastrar o cliente (a comparação normaliza dígitos)."""
import pytest
import uuid


pytestmark = pytest.mark.anyio


async def test_match_requires_auth(client):
    res = await client.get("/api/v1/clients/match", params={"cpf_cnpj": "12345678900"})
    assert res.status_code == 401


async def test_match_cpf_exato_ignora_mascara(client, auth_headers: dict):
    # dígitos derivados de um uuid aleatório — evita colidir com CPFs de
    # clientes deixados por execuções anteriores deste teste no mesmo banco.
    digitos = "".join(c for c in uuid.uuid4().hex if c.isdigit())[:9] or "123456789"
    cpf = f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-35"
    nome = f"Fulano de Tal Match {uuid.uuid4().hex[:6]}"
    create_res = await client.post(
        "/api/v1/clients",
        json={"tipo": "PF", "nome_completo": nome, "cpf": cpf},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Não foi possível criar cliente de teste")
    client_id = create_res.json()["id"]

    # mesma pessoa, CPF digitado sem máscara — precisa achar o mesmo cliente
    # mesmo o valor estar cifrado com um IV diferente a cada encrypt().
    res = await client.get(
        "/api/v1/clients/match",
        params={"cpf_cnpj": digitos + "35"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["match"] is not None
    assert data["match"]["id"] == client_id


async def test_match_cpf_sem_correspondencia_e_null(client, auth_headers: dict):
    cpf_inexistente = "".join(c for c in uuid.uuid4().hex if c.isdigit())[:11] or "99988877766"
    res = await client.get(
        "/api/v1/clients/match",
        params={"cpf_cnpj": cpf_inexistente},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["match"] is None


async def test_match_nome_parecido_vira_sugestao_nao_match(client, auth_headers: dict):
    nome = f"Beltrano Sugestao Teste {uuid.uuid4().hex[:6]}"
    create_res = await client.post(
        "/api/v1/clients",
        json={"tipo": "PF", "nome_completo": nome},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Não foi possível criar cliente de teste")
    client_id = create_res.json()["id"]

    res = await client.get(
        "/api/v1/clients/match",
        params={"nome": nome[:15]},
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["match"] is None
    assert any(s["id"] == client_id for s in data["sugestoes"])
