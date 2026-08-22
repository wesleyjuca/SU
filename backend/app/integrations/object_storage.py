"""Cliente de object storage S3-compatível (AWS S3 / R2 / MinIO / Railway) —
Fase 141, ver CLAUDE.md "Storage de documentos". Só busca/envia bytes; não
persiste nada no Postgres — quem decide o que fazer com o resultado é o
chamador (app/api/v1/documents.py, app/workers/tasks/ocr_tasks.py).

Único módulo desta base que usa um SDK (aioboto3) em vez de REST cru via
httpx — desvio deliberado: assinatura SigV4 é complexa o bastante
(assinatura de requisição, URLs pré-assinadas, uploads em chunks) que
reimplementar à mão é risco de segurança maior que a dependência extra."""
import re

import structlog

log = structlog.get_logger()


class ObjectStorageError(Exception):
    """Falha de comunicação com o object storage (rede, credenciais, bucket)."""


def is_configured() -> bool:
    from app.config import settings
    return bool(settings.S3_BUCKET and settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY)


def _client_kwargs() -> dict:
    from app.config import settings
    from botocore.config import Config as BotoConfig

    kwargs = {
        "aws_access_key_id": settings.S3_ACCESS_KEY_ID,
        "aws_secret_access_key": settings.S3_SECRET_ACCESS_KEY,
        "region_name": settings.S3_REGION or "auto",
        "config": BotoConfig(s3={"addressing_style": settings.S3_ADDRESSING_STYLE or "path"}),
    }
    if settings.S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
    return kwargs


def build_key(tenant_id, document_id, filename: str) -> str:
    """documents/{tenant_id}/{document_id}/{filename-sanitizado} — o
    tenant_id na própria key é defesa em profundidade além do filtro
    tenant_id já aplicado em todo query ORM (uma key nunca aponta pro
    objeto de outro tenant mesmo se alguém só souber o document_id)."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", (filename or "arquivo").strip())[:150] or "arquivo"
    return f"documents/{tenant_id}/{document_id}/{safe}"


async def upload_bytes(tenant_id, document_id, filename: str, content_type: str, data: bytes) -> str:
    import aioboto3
    from app.config import settings

    key = build_key(tenant_id, document_id, filename)
    try:
        session = aioboto3.Session()
        async with session.client("s3", **_client_kwargs()) as client:
            await client.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=data, ContentType=content_type)
    except Exception as exc:
        log.error("object_storage_upload_failed", key=key, error=str(exc))
        raise ObjectStorageError(str(exc)) from exc
    return key


async def get_bytes(key: str) -> bytes:
    import aioboto3
    from app.config import settings

    try:
        session = aioboto3.Session()
        async with session.client("s3", **_client_kwargs()) as client:
            resp = await client.get_object(Bucket=settings.S3_BUCKET, Key=key)
            async with resp["Body"] as stream:
                return await stream.read()
    except Exception as exc:
        log.error("object_storage_fetch_failed", key=key, error=str(exc))
        raise ObjectStorageError(str(exc)) from exc


async def delete_bytes(key: str) -> None:
    import aioboto3
    from app.config import settings

    try:
        session = aioboto3.Session()
        async with session.client("s3", **_client_kwargs()) as client:
            await client.delete_object(Bucket=settings.S3_BUCKET, Key=key)
    except Exception as exc:
        log.error("object_storage_delete_failed", key=key, error=str(exc))
        raise ObjectStorageError(str(exc)) from exc


async def generate_presigned_url(key: str, filename: str | None = None, expires_in: int = 300) -> str:
    import aioboto3
    from app.config import settings

    params = {"Bucket": settings.S3_BUCKET, "Key": key}
    if filename:
        params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
    try:
        session = aioboto3.Session()
        async with session.client("s3", **_client_kwargs()) as client:
            return await client.generate_presigned_url("get_object", Params=params, ExpiresIn=expires_in)
    except Exception as exc:
        log.error("object_storage_presign_failed", key=key, error=str(exc))
        raise ObjectStorageError(str(exc)) from exc
