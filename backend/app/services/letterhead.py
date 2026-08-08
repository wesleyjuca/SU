"""Resolução do logo do timbrado do escritório (Fase 143) — TenantConfig.
logo_url tinha o mesmo padrão base64-no-Postgres que Document.arquivo_url
tinha antes da Fase 141. Decide entre o caminho novo (bytes no object
storage S3-compatível, Fase 141) e o legado (base64 inline ou URL externa
literal em logo_url), sem que app/utils/pdf_builder.py precise mudar uma
linha — ele continua exigindo um `data:...;base64,...` completo nos 3
pontos onde decodifica o logo pra embutir no PDF."""
import base64

import structlog

from app.integrations import object_storage
from app.models.tenant import TenantConfig

log = structlog.get_logger()


async def resolve_logo_data_url(cfg: TenantConfig | None) -> str | None:
    """Devolve um `data:<mimetype>;base64,<bytes>` pronto pro pdf_builder
    embutir, ou `None` se não há logo. Se `cfg.logo_storage_key` está
    setado, busca os bytes no object storage e remonta o data URL em
    memória (nunca persistido); senão devolve `cfg.logo_url` como está
    (caminho legado — já é um data URL ou uma URL externa literal)."""
    if not cfg:
        return None
    if cfg.logo_storage_key:
        try:
            raw = await object_storage.get_bytes(cfg.logo_storage_key)
        except object_storage.ObjectStorageError as exc:
            log.warning("letterhead_logo_fetch_failed", key=cfg.logo_storage_key, error=str(exc))
            return None
        mimetype = cfg.logo_mimetype or "image/png"
        return f"data:{mimetype};base64," + base64.b64encode(raw).decode()
    return cfg.logo_url
