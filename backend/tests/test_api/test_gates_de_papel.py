"""Guarda dos gates de papel: cada rota, com token real de cada papel.

Por que existe: `nav.ts` esconde telas por papel, mas **menu não protege nada**
— não há guard de rota por papel fora de `/admin/*`, então bastava digitar a
URL (ou chamar a API direto) para alcançar o endpoint. Uma auditoria encontrou
rotas em telas restritas a gestão/ADV que o backend servia a qualquer papel
staff, incluindo o faturamento do escritório inteiro e o disparo de IA (que
gasta o orçamento do tenant).

A contradição que provou ser descuido e não política: `/financial/summary`
devolvia 403 para papel baixo enquanto `/system/analytics/financeiro` devolvia
200 — mesma tabela, mesmo tenant, mesma camada de router; só mudava a
dependência declarada na assinatura.

Este teste percorre a matriz rota × papel e exige as DUAS direções: o papel
baixo é barrado E o papel legítimo continua passando. Só a primeira metade
deixaria passar uma correção que trancasse todo mundo.
"""
import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.user import User
from tests.db_isolada import sessao_isolada

pytestmark = pytest.mark.asyncio

PAPEIS_TESTE = ["ASSISTENTE", "PARALEGAL", "GESTOR", "ADVOGADO", "SOCIO"]

# (método, rota) -> papéis que DEVEM passar. `None` = rota propositalmente
# aberta a qualquer papel staff (controle: pega uma correção larga demais).
# SUPERADMIN atravessa qualquer `require_role` por desenho
# (`dependencies.py`), por isso não aparece nas listas.
MATRIZ: dict[tuple[str, str], set[str] | None] = {
    ("GET", "/api/v1/system/analytics/financeiro"): {"ADMIN", "SOCIO", "GESTOR"},
    ("GET", "/api/v1/system/analytics/processos"): {"ADMIN", "SOCIO", "GESTOR"},
    ("GET", "/api/v1/system/analytics/agentes"): {"ADMIN", "SOCIO", "GESTOR"},
    ("GET", "/api/v1/integrations/hub"): {"ADMIN"},
    ("GET", "/api/v1/integrations/hub/google_drive_doutrina/last-sync"): {"ADMIN"},
    ("GET", "/api/v1/integrations/hub/google_drive_doutrina/last-sync/arquivos"): {"ADMIN"},
    ("GET", "/api/v1/petition-templates"): {"ADMIN", "SOCIO", "ADVOGADO"},
    ("GET", "/api/v1/approvals"): {"ADMIN", "SOCIO", "ADVOGADO"},
    # Gasto de IA — decisão de produto registrada nesta fase.
    ("POST", "/api/v1/agents/trigger"): {"ADMIN", "SOCIO", "ADVOGADO"},
    ("POST", "/api/v1/documents/petitions/generate"): {"ADMIN", "SOCIO", "ADVOGADO"},
    # Controle: devem seguir abertas (as telas que as consomem são roles:null).
    ("GET", "/api/v1/clients"): None,
    ("GET", "/api/v1/system/metrics"): None,
}


@pytest.fixture
async def usuarios_por_papel(client, test_user):
    """Cria um usuário real por papel no tenant do ADMIN semeado e devolve os
    tokens. Remove todos ao final, mesmo se o teste falhar."""
    async with sessao_isolada() as db:
        admin = (await db.execute(
            select(User).where(User.email == test_user["email"])
        )).scalar_one_or_none()
        if admin is None:
            pytest.skip("ADMIN semeado não disponível neste ambiente")
        tenant_id = admin.tenant_id
        criados = []
        for papel in PAPEIS_TESTE:
            # Domínio real: `EmailStr` rejeita domínios reservados (.local).
            email = f"gate-{papel.lower()}-{uuid.uuid4().hex[:8]}@teste.afjadvogados.com.br"
            usuario = User(
                email=email, hashed_password=hash_password("Gate@123"),
                full_name=f"Teste {papel}", role=papel, tenant_id=tenant_id, is_active=True,
            )
            db.add(usuario)
            criados.append((papel, email, usuario))
        await db.commit()
        ids = [u.id for _, _, u in criados]

    try:
        tokens = {}
        res = await client.post("/api/v1/auth/login", json=test_user)
        if res.status_code != 200:
            pytest.skip("Login do ADMIN falhou — seed não disponível")
        tokens["ADMIN"] = res.json()["access_token"]
        for papel, email, _ in criados:
            res = await client.post("/api/v1/auth/login", json={"email": email, "password": "Gate@123"})
            assert res.status_code == 200, f"login {papel}: {res.status_code}"
            tokens[papel] = res.json()["access_token"]
        yield tokens
    finally:
        async with sessao_isolada() as db:
            await db.execute(User.__table__.delete().where(User.id.in_(ids)))
            await db.commit()


async def test_matriz_de_papel_por_rota(client, usuarios_por_papel):
    problemas = []
    verificacoes = 0

    for (metodo, rota), permitidos in MATRIZ.items():
        for papel, token in usuarios_por_papel.items():
            headers = {"Authorization": f"Bearer {token}"}
            if metodo == "GET":
                resp = await client.get(rota, headers=headers)
            else:
                resp = await client.post(rota, json={}, headers=headers)
            verificacoes += 1
            barrado = resp.status_code == 403

            if permitidos is None:
                if barrado:
                    problemas.append(
                        f"{metodo} {rota}: {papel} recebeu 403 numa rota que deve seguir aberta"
                    )
            elif papel in permitidos:
                if barrado:
                    problemas.append(f"{metodo} {rota}: {papel} DEVERIA passar, recebeu 403")
            elif not barrado:
                problemas.append(
                    f"{metodo} {rota}: {papel} NÃO foi barrado (status {resp.status_code})"
                )

    assert verificacoes == len(MATRIZ) * (len(PAPEIS_TESTE) + 1)
    assert not problemas, "\n".join(problemas)
