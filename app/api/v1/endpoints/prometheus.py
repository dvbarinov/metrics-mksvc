from fastapi import APIRouter, Response, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.exporters.prometheus_exporter import exporter
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import asyncio

router = APIRouter()


@router.get("/metrics", response_class=Response)
async def prometheus_metrics(
        session: AsyncSession = Depends(get_session)
):
    """
    Экспорт метрик в формате Prometheus.

    Prometheus будет опрашивать этот эндпоинт для сбора метрик.
    Все теги автоматически конвертируются в лейблы.
    """
    # Собираем метрики из БД
    metrics_data = await exporter.collect_metrics(session, window_minutes=5)

    # Генерируем формат Prometheus
    prometheus_output = exporter.generate_prometheus_metrics(metrics_data)

    return Response(
        content=prometheus_output,
        media_type=CONTENT_TYPE_LATEST
    )


@router.get("/metrics/debug")
async def debug_metrics(
        session: AsyncSession = Depends(get_session)
):
    """
    Отладочный эндпоинт - возвращает метрики в JSON формате
    """
    metrics_data = await exporter.collect_metrics(session, window_minutes=5)
    return metrics_data
