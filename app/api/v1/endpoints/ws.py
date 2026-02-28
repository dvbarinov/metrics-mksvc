from fastapi import APIRouter, WebSocket, Query
from typing import Optional
import json

from app.core.broadcaster import manager

router = APIRouter()


@router.websocket("/live")
async def websocket_endpoint(
        websocket: WebSocket,
        tags_filter: Optional[str] = Query(None),
        group_by: Optional[str] = Query(None)
):
    """
    WebSocket для получения агрегированных метрик в реальном времени.

    Параметры:
    - tags_filter: JSON фильтр, например: {"env":"prod","region":"eu-west"}
    - group_by: список тегов для группировки, например: ["region","version"]
    """
    subscription = {}

    if tags_filter:
        try:
            subscription["filter"] = json.loads(tags_filter)
        except json.JSONDecodeError:
            await websocket.close(code=1003)  # Unsupported data
            return

    if group_by:
        try:
            subscription["group_by"] = json.loads(group_by)
        except json.JSONDecodeError:
            await websocket.close(code=1003)
            return

    await manager.connect(websocket, subscription)

    try:
        # Keep-alive: клиент может отправлять ping
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except Exception:
        manager.disconnect(websocket)
