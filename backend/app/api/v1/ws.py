"""WebSocket endpoint para updates em tempo real."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import JWTError
from app.core.security import decode_access_token
from app.db.redis import get_redis
import asyncio
import json
import structlog

log = structlog.get_logger()
router = APIRouter(tags=["websocket"])

# Conexões ativas: user_id → set de WebSockets
_connections: dict[str, set[WebSocket]] = {}


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(...),
):
    # Autenticar via token na query string
    try:
        payload = decode_access_token(token)
        if payload.get("sub") != user_id:
            await websocket.close(code=4001)
            return
        # Token revogado (logout) não deve manter a conexão viva até expirar.
        from app.core.security import is_token_blacklisted
        jti = payload.get("jti", "")
        if jti and await is_token_blacklisted(jti):
            await websocket.close(code=4001)
            return
    except JWTError:
        await websocket.close(code=4001)
        return

    # Usuário desativado não conecta (revogação imediata de acesso).
    try:
        import uuid as _uuid
        from sqlalchemy import select
        from app.db.base import AsyncSessionLocal
        from app.models.user import User
        async with AsyncSessionLocal() as _db:
            active = (await _db.execute(
                select(User.is_active).where(User.id == _uuid.UUID(user_id))
            )).scalar_one_or_none()
        if not active:
            await websocket.close(code=4001)
            return
    except Exception:
        pass

    await websocket.accept()
    _connections.setdefault(user_id, set()).add(websocket)
    log.info("ws_connected", user_id=user_id)

    redis = await get_redis()
    if not redis:
        await websocket.send_json({"type": "CONNECTED", "user_id": user_id, "warning": "realtime_unavailable"})
        try:
            while True:
                await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
        except (asyncio.TimeoutError, WebSocketDisconnect):
            pass
        _connections.get(user_id, set()).discard(websocket)
        return

    channel = f"user:{user_id}:events"

    try:
        # Subscrever no canal Redis pub/sub do usuário
        async with redis.pubsub() as pubsub:
            await pubsub.subscribe(channel)
            await websocket.send_json({"type": "CONNECTED", "user_id": user_id})

            async def _listen_redis():
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            await websocket.send_json(data)
                        except Exception:
                            pass

            # Rodar listener e keepalive em paralelo
            redis_task = asyncio.create_task(_listen_redis())

            while True:
                try:
                    # Ping keepalive a cada 30s
                    await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "PING"})
                    # Aguardar PONG por 10s; fechar se cliente não responder
                    try:
                        pong = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
                        if pong != "PONG":
                            break
                    except asyncio.TimeoutError:
                        break
                except WebSocketDisconnect:
                    break

            redis_task.cancel()

    except WebSocketDisconnect:
        pass
    finally:
        _connections.get(user_id, set()).discard(websocket)
        log.info("ws_disconnected", user_id=user_id)


async def publish_event(user_id: str, event_type: str, data: dict):
    """Publica evento para um usuário via Redis pub/sub."""
    try:
        redis = await get_redis()
        payload = json.dumps({"type": event_type, **data})
        await redis.publish(f"user:{user_id}:events", payload)
    except Exception as exc:
        log.warning("ws_publish_failed", user_id=user_id, error=str(exc))


async def broadcast_event(event_type: str, data: dict):
    """Broadcast para todos os usuários conectados."""
    for user_id in list(_connections.keys()):
        await publish_event(user_id, event_type, data)
