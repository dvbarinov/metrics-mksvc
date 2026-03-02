import logging
import asyncio
from fastapi import WebSocket
from typing import Set, Dict, Optional
from app.utils.aggregators import aggregate_last_window
from app.schemas.metric import AggregatedMetric

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        # Подписки: какой клиент какие теги слушает
        self.subscriptions: Dict[WebSocket, Dict] = {}

    async def connect(self, websocket: WebSocket, subscription: Dict = None):
        await websocket.accept()
        self.active_connections.add(websocket)
        self.subscriptions[websocket] = subscription or {}
        logger.info(f"🔌 WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        self.subscriptions.pop(websocket, None)
        logger.info(f"🔌 WebSocket disconnected. Total: {len(self.active_connections)}")

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


async def metrics_aggregator():
    """Фоновая задача агрегации с группировкой по тегам; с защитой от падений БД"""
    while True:
        try:
            # Агрегируем по регионам и версиям
            agg_list = await aggregate_last_window(
                window_seconds=30,
                group_by_tags=["region", "version"],
                filter_tags={"env": "production"}
            )

            if agg_list:
                # Отправляем каждый агрегат отдельно
                for agg in agg_list:
                    payload = AggregatedMetric(**agg).model_dump_json()
                    await manager.broadcast(payload)

        except Exception as e:
            # Логируем ошибку, но не останавливаем цикл
            logger.warning(f"⚠️ Aggregation error (will retry): {e}")

        await asyncio.sleep(5)
