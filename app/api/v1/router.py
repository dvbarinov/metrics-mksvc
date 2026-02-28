from fastapi import APIRouter
from app.api.v1.endpoints import metrics, ws

# Создаем главный роутер для версии API v1
api_router = APIRouter()

# Подключаем роутеры эндпоинтов
# prefix добавляется ко всем путям внутри этих модулей
api_router.include_router(
    metrics.router,
    prefix="/metrics",
    tags=["Metrics"]
)

api_router.include_router(
    ws.router,
    prefix="/ws",
    tags=["WebSocket"]
)

# Экспортируем список роутеров для подключения в main.py
# Это позволяет легко добавлять новые версии API (v2, v3)
__all__ = ["api_router"]
