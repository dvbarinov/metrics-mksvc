from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session, async_session_maker
from app.models.metric import Metric
from datetime import datetime, timedelta
from typing import List, Dict, Optional


async def aggregate_last_window(
        window_seconds: int = 30,
        group_by_tags: Optional[List[str]] = None,
        filter_tags: Optional[Dict[str, str]] = None
) -> List[Dict]:
    async with async_session_maker() as session:
        since = datetime.utcnow() - timedelta(seconds=window_seconds)

        # Базовые колонки
        columns = [
            Metric.service_name,
            Metric.metric_name,
            func.avg(Metric.value).label("avg_value"),
            func.min(Metric.value).label("min_value"),
            func.max(Metric.value).label("max_value"),
            func.count(Metric.value).label("count"),
        ]

        # Percentiles (работает в PostgreSQL 9.4+)
        # Используем text() для сложных функций, если стандартные не работают
        columns.append(func.percentile_cont(0.5).within_group(Metric.value.asc()).label("p50"))
        columns.append(func.percentile_cont(0.95).within_group(Metric.value.asc()).label("p95"))
        columns.append(func.percentile_cont(0.99).within_group(Metric.value.asc()).label("p99"))

        query = select(
            Metric.service_name,
            Metric.metric_name,
            func.avg(Metric.value).label("avg_value"),
            func.count(Metric.value).label("count")
        ).where(Metric.timestamp >= since)

        # Фильтрация по тегам
        if filter_tags:
            for key, value in filter_tags.items():
                # Используем оператор @> для JSONB или доступ по ключу
                query = query.where(Metric.tags[key].astext == value)

        # Группировка
        group_by_cols = [Metric.service_name, Metric.metric_name]

        if group_by_tags:
            for tag_key in group_by_tags:
                tag_label = f"tag_{tag_key}"
                columns.append(Metric.tags[tag_key].astext.label(tag_label))
                group_by_cols.append(Metric.tags[tag_key].astext)

        # Пересобираем query с новыми колонками если были теги
        if group_by_tags:
            query = select(*columns).where(Metric.timestamp >= since)
            if filter_tags:
                for key, value in filter_tags.items():
                    query = query.where(Metric.tags[key].astext == value)
            query = query.group_by(*group_by_cols).order_by(Metric.service_name, Metric.metric_name)
        else:
            query = query.group_by(*group_by_cols).order_by(Metric.service_name, Metric.metric_name)

        result = await session.execute(query)
        rows = result.fetchall()

        aggregates = []
        for row in rows:
            agg = {
                "service_name": row.service_name,
                "metric_name": row.metric_name,
                "avg_value": float(row.avg_value) if row.avg_value else 0.0,
                "min_value": float(row.min_value) if row.min_value else 0.0,
                "max_value": float(row.max_value) if row.max_value else 0.0,
                "p50": float(row.p50) if row.p50 else None,
                "p95": float(row.p95) if row.p95 else None,
                "p99": float(row.p99) if row.p99 else None,
                "count": row.count,
                "window_seconds": window_seconds,
                "tags": {}
            }

            if group_by_tags:
                for tag_key in group_by_tags:
                    tag_value = getattr(row, f"tag_{tag_key}", None)
                    if tag_value:
                        agg["tags"][tag_key] = tag_value

            aggregates.append(agg)

        return aggregates
