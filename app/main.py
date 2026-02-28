import asyncio
import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.api.v1.router import api_router
from app.core.db import init_db, close_db
from app.core.broadcaster import metrics_aggregator, manager
from prometheus_fastapi_instrumentator import Instrumentator

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# --- Lifespan Events ---
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Управление жизненным циклом приложения.
    Запуск и остановка фоновых задач, подключение к БД.
    """
    # Startup
    logger.info("🚀 Starting up application...")

    try:
        # Инициализация таблиц БД (в продакшене лучше через Alembic)
        if os.getenv("AUTO_MIGRATE", "false").lower() == "true":
            await init_db()
            logger.info("✅ Database tables initialized")

        # Запуск фоновой задачи агрегации метрик
        aggregator_task = asyncio.create_task(metrics_aggregator())
        logger.info("📊 Metrics aggregator started")

        yield

    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise

    finally:
        # Shutdown
        logger.info("🛑 Shutting down application...")

        # Отмена фоновой задачи
        if 'aggregator_task' in locals():
            aggregator_task.cancel()
            try:
                await aggregator_task
            except asyncio.CancelledError:
                pass

        # Закрытие соединений с БД
        await close_db()

        # Отключение всех WebSocket клиентов
        for connection in list(manager.active_connections):
            await connection.close()

        logger.info("✅ Shutdown complete")


# --- Application Factory ---
def create_app() -> FastAPI:
    """Фабрика приложения для гибкой конфигурации."""

    app = FastAPI(
        title="Real-time Metrics Dashboard",
        description="Микросервис для сбора и визуализации метрик в реальном времени с поддержкой тегов",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # --- Middleware ---

    # CORS (разрешаем запросы с фронтенда)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Exception Handlers ---

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Кастомная обработка ошибок валидации Pydantic."""
        logger.warning(f"Validation error: {exc.errors()}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Validation Error",
                "errors": exc.errors()
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Обработка непредвиденных ошибок."""
        logger.error(f"Internal error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal Server Error"},
        )

    # --- Routers ---

    # Подключаем API роутеры
    app.include_router(api_router, prefix="/api/v1")

    # Health check endpoint (для Kubernetes / Load Balancer)
    @app.get("/health", tags=["Health"])
    async def health_check():
        return {
            "status": "healthy",
            "websocket_connections": len(manager.active_connections)
        }

    # Root endpoint
    @app.get("/", tags=["Root"])
    async def root():
        return {
            "message": "Metrics Dashboard API",
            "docs": "/docs",
            "health": "/health"
        }

    # --- Prometheus Metrics ---

    # Инструментация для Prometheus (опционально)
    if os.getenv("ENABLE_PROMETHEUS", "true").lower() == "true":
        Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    return app


# --- Entry Point ---
# Создаем экземпляр приложения для uvicorn
app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=os.getenv("DEBUG", "false").lower() == "true",
        log_level="info",
    )
