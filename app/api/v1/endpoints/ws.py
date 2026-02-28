from fastapi import APIRouter, WebSocket
from app.core.broadcaster import manager

router = APIRouter()

@router.websocket("/live")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep alive or handle commands
    except Exception:
        manager.disconnect(websocket)
        