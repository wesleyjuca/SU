from sqlalchemy import String, Boolean, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy import DateTime, func
import uuid
from datetime import datetime
from app.db.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    subdomain: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    plan: Mapped[str] = mapped_column(String(50), default="STANDARD")
    # Fase 170 — só o tenant raiz (slug="afj") deve ter isento=True; garantido
    # pelo backfill idempotente em app/core/events.py, não editável via API.
    isento: Mapped[bool] = mapped_column(Boolean, default=False)
    # Fase 199 — tenant público de demonstração (slug="demo"). Garantido pelo
    # mesmo backfill idempotente da Fase 170 (app/core/events.py), roda em
    # todo boot; não editável via API. Incompatível com isento (nunca deve
    # haver overlap entre "tenant raiz da plataforma" e "tenant de brinquedo
    # público" — o próprio backfill garante isso).
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Fase 180 — enquanto False ("em construção"), SUPERADMIN pode excluir
    # processos/usuários de verdade (cascata real, dado de teste). Uma vez
    # True ("em produção"), os 2 endpoints de exclusão permanente passam a
    # recusar (403) e orientam usar arquivar/desativar — trava de segurança
    # contra apagar dado real por engano depois que o escritório for pra
    # produção. Editável só por SUPERADMIN via PUT /tenants/{id}.
    em_producao: Mapped[bool] = mapped_column(Boolean, default=False)
    # Unidades da mesma banca: unidade (child) aponta para a banca-mãe (parent).
    # Isolamento de dados preservado (cada tenant filtra por tenant_id); o vínculo
    # serve só para agrupamento e relatórios consolidados futuros (P3).
    parent_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True
    )
    unit_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    max_users: Mapped[int] = mapped_column(Integer, default=10)
    max_storage_gb: Mapped[int] = mapped_column(Integer, default=50)
    # Fase 230 — endereço físico do próprio escritório (mesmo formato de
    # Client.endereco_json: {cep, logradouro, bairro, cidade, uf, latitude,
    # longitude}), groundwork pro mapa com marcadores de escritório+clientes
    # planejado pra uma fase futura. Geocodificado via BrasilAPI no momento
    # do save (ver _geocodificar_endereco em app/api/v1/clients.py).
    endereco_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    config: Mapped["TenantConfig | None"] = relationship(back_populates="tenant", uselist=False)


class TenantConfig(Base):
    __tablename__ = "tenant_configs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Branding
    primary_color: Mapped[str] = mapped_column(String(20), default="#C9A84C")
    secondary_color: Mapped[str] = mapped_column(String(20), default="#1A1A1A")
    accent_color: Mapped[str] = mapped_column(String(20), default="#F5F0E8")
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Fase 143: logo migrado pra object storage S3-compatível (mesmo padrão
    # de Document.arquivo_storage_key na Fase 141) — NULL = logo_url acima
    # ainda vale (base64 inline ou URL externa literal), setado = logo vive
    # no S3 nessa key (logo_url fica NULL pra essas linhas).
    logo_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_mimetype: Mapped[str | None] = mapped_column(String(150), nullable=True)
    logo_dark_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    favicon_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_name: Mapped[str] = mapped_column(String(255), default="AFJ CORE")

    # Layout
    nav_config: Mapped[list | None] = mapped_column(JSONB, default=list)
    dashboard_widgets: Mapped[list | None] = mapped_column(JSONB, default=list)

    # Módulos
    modules_enabled: Mapped[dict | None] = mapped_column(
        JSONB,
        default=lambda: {
            "processos": True,
            "peticoes": True,
            "clientes": True,
            "financeiro": True,
            "agentes": True,
            "visual_law": True,
        },
    )

    document_templates: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    custom_css: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant: Mapped["Tenant"] = relationship(back_populates="config")
