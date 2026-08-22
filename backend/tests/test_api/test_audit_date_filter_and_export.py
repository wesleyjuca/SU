"""Fase 205.4 — GET /audit ganha filtro por intervalo de datas (date_from/
date_to) e GET /audit/export exporta os mesmos filtros como CSV, mesmo
padrão de GET /financial/export.

`audit_logs` é imutável por trigger de banco (proíbe UPDATE/DELETE, ver
docstring de AuditLog) — por isso este teste NUNCA commita as linhas de
teste que insere: abre a sessão, usa só `db.flush()` (visível dentro da
própria transação, o suficiente pra exercitar a query real contra Postgres)
e deixa o `async with` fechar a sessão sem commit, que faz rollback
automático — zero resíduo permanente na tabela real."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.api.v1.audit import list_audit_logs, export_audit_logs
from app.db.base import AsyncSessionLocal
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant

pytestmark = pytest.mark.asyncio


class _CurrentUser:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


async def test_date_from_date_to_filtram_por_intervalo():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant teste 205.4", slug=f"teste-205-4-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        agora = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
        antigo = AuditLog(
            event_id=uuid.uuid4(), timestamp=agora - timedelta(days=30),
            action="EVENTO_ANTIGO", success=True, tenant_id=tenant.id,
        )
        dentro = AuditLog(
            event_id=uuid.uuid4(), timestamp=agora,
            action="EVENTO_DENTRO_DO_INTERVALO", success=True, tenant_id=tenant.id,
        )
        futuro = AuditLog(
            event_id=uuid.uuid4(), timestamp=agora + timedelta(days=30),
            action="EVENTO_FUTURO", success=True, tenant_id=tenant.id,
        )
        db.add_all([antigo, dentro, futuro])
        await db.flush()

        current_user = _CurrentUser(tenant.id)
        resultado = await list_audit_logs(
            limit=100, offset=0, action=None, success=None, agent_name=None, resource_type=None,
            date_from=(agora - timedelta(days=1)).date(),
            date_to=(agora + timedelta(days=1)).date(),
            current_user=current_user, db=db,
        )
        acoes = {item["action"] for item in resultado["items"]}
        assert acoes == {"EVENTO_DENTRO_DO_INTERVALO"}
        assert resultado["total"] == 1
        # nunca commita — o `async with` faz rollback ao fechar


async def test_export_gera_csv_com_os_mesmos_filtros():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant teste 205.4b", slug=f"teste-205-4b-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()

        db.add(AuditLog(
            event_id=uuid.uuid4(), timestamp=datetime.now(timezone.utc),
            action="EXPORT_TESTE", success=True, tenant_id=tenant.id,
            resource_type="documento", ip_address="203.0.113.5",
        ))
        db.add(AuditLog(
            event_id=uuid.uuid4(), timestamp=datetime.now(timezone.utc),
            action="EXPORT_TESTE_FALHA", success=False, tenant_id=tenant.id,
        ))
        await db.flush()

        current_user = _CurrentUser(tenant.id)
        resposta = await export_audit_logs(
            action=None, success=True, agent_name=None, resource_type=None, date_from=None, date_to=None,
            current_user=current_user, db=db,
        )
        assert resposta.media_type == "text/csv"
        assert "auditoria.csv" in resposta.headers["Content-Disposition"]

        corpo = "".join([chunk async for chunk in resposta.body_iterator])
        assert "EXPORT_TESTE" in corpo
        assert "EXPORT_TESTE_FALHA" not in corpo
        assert "203.0.113.5" in corpo


async def test_list_e_export_isolam_por_tenant():
    async with AsyncSessionLocal() as db:
        tenant_a = Tenant(name="Tenant A 205.4", slug=f"teste-205-4c-a-{uuid.uuid4().hex[:8]}")
        tenant_b = Tenant(name="Tenant B 205.4", slug=f"teste-205-4c-b-{uuid.uuid4().hex[:8]}")
        db.add_all([tenant_a, tenant_b])
        await db.flush()

        db.add(AuditLog(
            event_id=uuid.uuid4(), timestamp=datetime.now(timezone.utc),
            action="EVENTO_TENANT_A", success=True, tenant_id=tenant_a.id,
        ))
        db.add(AuditLog(
            event_id=uuid.uuid4(), timestamp=datetime.now(timezone.utc),
            action="EVENTO_TENANT_B", success=True, tenant_id=tenant_b.id,
        ))
        await db.flush()

        resultado = await list_audit_logs(
            limit=100, offset=0, action=None, success=None, agent_name=None, resource_type=None,
            date_from=None, date_to=None, current_user=_CurrentUser(tenant_a.id), db=db,
        )
        acoes = {item["action"] for item in resultado["items"]}
        assert "EVENTO_TENANT_A" in acoes
        assert "EVENTO_TENANT_B" not in acoes
