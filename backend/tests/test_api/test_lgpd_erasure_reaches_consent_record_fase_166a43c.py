"""Rodada pós-166a43c (achado real de auditoria) — `LGPDConsentRecord`
(`client_id` FK + `ip_address` PII) nunca era tocada por
`erase_client_data`/`export_client_data`. Hoje nenhum endpoint escreve
nessa tabela (só `demo_reset.py` apaga em bulk pro tenant demo) — sem
endpoint próprio pra semear, a linha é inserida direto via ORM, mesmo
padrão já usado quando não há caminho HTTP de criação."""
import uuid

import pytest
from httpx import AsyncClient

from app.db.base import AsyncSessionLocal
from app.models.audit_log import LGPDConsentRecord

pytestmark = pytest.mark.anyio


async def test_lgpd_erasure_reaches_consent_record(client: AsyncClient, auth_headers: dict):
    create_res = await client.post(
        "/api/v1/clients",
        json={"tipo": "PF", "nome_completo": "Titular ConsentRecord 166a43c", "lgpd_consent": True},
        headers=auth_headers,
    )
    if create_res.status_code != 201:
        pytest.skip("Could not create client")
    client_id = create_res.json()["id"]
    ip_marcador = "203.0.113.199"

    async with AsyncSessionLocal() as db:
        db.add(LGPDConsentRecord(
            client_id=uuid.UUID(client_id),
            tipo_dado="dados_pessoais",
            consentimento=True,
            base_legal="consentimento",
            ip_address=ip_marcador,
            texto_versao="v1",
        ))
        await db.commit()

    try:
        export_antes = await client.get(f"/api/v1/lgpd/clients/{client_id}/export", headers=auth_headers)
        assert export_antes.status_code == 200
        consentimentos_antes = export_antes.json().get("consentimentos_lgpd", [])
        assert len(consentimentos_antes) == 1
        assert consentimentos_antes[0]["ip_address"] == ip_marcador

        erase_res = await client.delete(f"/api/v1/lgpd/clients/{client_id}/data", headers=auth_headers)
        if erase_res.status_code != 200:
            pytest.skip("Erasure not permitted for this role")

        export_depois = await client.get(f"/api/v1/lgpd/clients/{client_id}/export", headers=auth_headers)
        assert export_depois.status_code == 200
        consentimentos_depois = export_depois.json().get("consentimentos_lgpd", [])
        assert len(consentimentos_depois) == 1
        # PII (IP) removido...
        assert consentimentos_depois[0]["ip_address"] is None
        # ...mas o metadado de auditoria de consentimento (não-PII) sobrevive.
        assert consentimentos_depois[0]["consentimento"] is True
        assert consentimentos_depois[0]["base_legal"] == "consentimento"
        assert consentimentos_depois[0]["tipo_dado"] == "dados_pessoais"
        assert ip_marcador not in str(export_depois.json())
    finally:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import text
            await db.execute(
                text("DELETE FROM lgpd_consent_records WHERE client_id = :cid"),
                {"cid": client_id},
            )
            await db.commit()
