import asyncio
import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import CONTENT_TYPE_LATEST

from app.api.v1.router import api_router
from app.core.db import init_db, close_db, check_db_connection
from app.core.broadcaster import metrics_aggregator, manager
from app.exporters.prometheus_exporter import exporter


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

    # 1. Проверка подключения к БД
    db_ok = await check_db_connection()
    if not db_ok:
        logger.error("❌ Cannot start without database connection")
        raise RuntimeError("Database connection failed")

    try:
        # Инициализация таблиц БД (в продакшене лучше через Alembic)
        if os.getenv("AUTO_MIGRATE", "true").lower() == "true":
            await init_db()
            logger.info("✅ Database tables initialized")

        # Запуск фоновой задачи агрегации метрик
        aggregator_task = asyncio.create_task(metrics_aggregator())
        logger.info("📊 Metrics aggregator started")

        # Инициализация инструментатора Prometheus
        Instrumentator(
            should_respond=lambda request: request.url.path != "/metrics/internal",
            metric_namespace="fastapi",
            metric_name="requests",
        ).instrument(app).expose(
            app,
            endpoint="/metrics/internal",
            should_gzip=True
        )
        logger.info("📈 Prometheus internal metrics enabled at /metrics/internal")

        yield

    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise e

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
        # Не возвращаем 500 для WebSocket, чтобы не закрывать соединение лишними ответами
        if request.url.path.startswith("/api/v1/ws"):
            return JSONResponse(status_code=200, content={"detail": "Internal Error"})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal Server Error"},
        )

    # --- Routers ---

    # Подключаем API роутеры
    app.include_router(api_router, prefix="/api/v1")

    # --- Prometheus Metrics Endpoint ---

    @app.get("/metrics", tags=["Prometheus"])
    async def prometheus_metrics(request: Request):
        """
        Экспорт метрик в формате Prometheus.

        Prometheus будет опрашивать этот эндпоинт для сбора метрик.
        Все теги автоматически конвертируются в лейблы.

        Формат ответа: text/plain; version=0.0.4; charset=utf-8
        """
        from app.core.db import get_session

        async for session in get_session():
            try:
                # Собираем метрики из БД
                metrics_data = await exporter.collect_metrics(session, window_minutes=5)

                # Генерируем формат Prometheus
                prometheus_output = exporter.generate_prometheus_metrics(metrics_data)

                return Response(
                    content=prometheus_output,
                    media_type=CONTENT_TYPE_LATEST,
                    headers={
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                        "Pragma": "no-cache",
                        "Expires": "0"
                    }
                )
            finally:
                await session.close()

    @app.get("/metrics/debug", tags=["Prometheus"])
    async def debug_metrics(request: Request):
        """
        Отладочный эндпоинт - возвращает метрики в JSON формате.
        Полезно для отладки перед экспортом в Prometheus.
        """
        from app.core.db import get_session

        async for session in get_session():
            try:
                metrics_data = await exporter.collect_metrics(session, window_minutes=5)
                return {
                    "metrics_count": len(metrics_data),
                    "metrics": metrics_data,
                    "cache_timestamp": exporter._cache_timestamp.isoformat() if exporter._cache_timestamp else None
                }
            finally:
                await session.close()

    # Health check endpoint (для Kubernetes / Load Balancer)
    @app.get("/health", tags=["Health"])
    async def health_check():
        return {
            "status": "healthy",
            "websocket_connections": len(manager.active_connections),
            "prometheus_enabled": True
        }

    # Readiness check (для Kubernetes)
    @app.get("/ready", tags=["Health"])
    async def readiness_check():
        db_ok = await check_db_connection()
        return {
            "ready": db_ok,
            "database": "connected" if db_ok else "disconnected",
            "prometheus": "enabled"
        }

    # Liveness check (для Kubernetes)
    @app.get("/live", tags=["Health"])
    async def liveness_check():
        return {"alive": True}

    # Root endpoint
    @app.get("/", tags=["Root"])
    async def root():
        return {
            "message": "Metrics Dashboard API",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/health",
            "ready": "/ready",
            "live": "/live",
            "prometheus_metrics": "/metrics",
            "prometheus_internal": "/metrics/internal",
            "prometheus_debug": "/metrics/debug"
        }

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
        access_log=True,
    )
