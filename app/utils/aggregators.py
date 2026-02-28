from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import async_session
from app.models.metric import Metric
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json


async def aggregate_last_window(
        window_seconds: int = 30,
        group_by_tags: Optional[List[str]] = None,
        filter_tags: Optional[Dict[str, str]] = None
) -> List[Dict]:
    """
    Агрегирует метрики за последние N секунд.

    Args:
        window_seconds: окно агрегации в секундах
        group_by_tags: список тегов для группировки (например: ["region", "version"])
        filter_tags: фильтр по тегам (например: {"env": "prod"})
    """
    async with async_session() as session:
        since = datetime.utcnow() - timedelta(seconds=window_seconds)

        # Базовый запрос
        query = select(
            Metric.service_name,
            Metric.metric_name,
            func.avg(Metric.value).label("avg_value"),
            func.min(Metric.value).label("min_value"),
            func.max(Metric.value).label("max_value"),
            func.count(Metric.value).label("count"),
            func.percentile_cont(0.5).within_group(Metric.value).label("p50"),
            func.percentile_cont(0.95).within_group(Metric.value).label("p95"),
            func.percentile_cont(0.99).within_group(Metric.value).label("p99")
        ).where(
            Metric.timestamp >= since
        )

        # Фильтрация по тегам
        if filter_tags:
            for key, value in filter_tags.items():
                query = query.where(Metric.tags[key].astext == value)

        # Группировка
        group_by_cols = [Metric.service_name, Metric.metric_name]

        if group_by_tags:
            # Добавляем теги в SELECT и GROUP BY
            for tag_key in group_by_tags:
                query = query.add_columns(
                    Metric.tags[tag_key].label(f"tag_{tag_key}")
                )
                group_by_cols.append(Metric.tags[tag_key])

        query = query.group_by(*group_by_cols).order_by(
            Metric.service_name,
            Metric.metric_name
        )

        result = await session.execute(query)
        rows = result.fetchall()

        aggregates = []
        for row in rows:
            agg = {
                "service_name": row.service_name,
                "metric_name": row.metric_name,
                "avg_value": float(row.avg_value),
                "min_value": float(row.min_value),
                "max_value": float(row.max_value),
                "p50": float(row.p50) if row.p50 else None,
                "p95": float(row.p95) if row.p95 else None,
                "p99": float(row.p99) if row.p99 else None,
                "count": row.count,
                "window_seconds": window_seconds,
                "tags": {}
            }

            # Извлекаем теги из результата
            if group_by_tags:
                for tag_key in group_by_tags:
                    tag_value = getattr(row, f"tag_{tag_key}", None)
                    if tag_value:
                        agg["tags"][tag_key] = tag_value

            aggregates.append(agg)

        return aggregates
    