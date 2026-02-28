from fastapi import WebSocket
from typing import Set
import asyncio
from app.utils.aggregators import aggregate_last_window
from app.schemas.metric import AggregatedMetric

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: str):
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.add(connection)
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

# Фоновая задача (запускается в startup event)
async def metrics_aggregator():
    while True:
        agg = await aggregate_last_window(window_seconds=30)  # см. ниже
        if agg:
            payload = AggregatedMetric(**agg).model_dump_json()
            await manager.broadcast(payload)
        await asyncio.sleep(5)  # обновление каждые 5 сек
