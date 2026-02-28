from sqlalchemy import select, func
from app.core.db import async_session
from app.models.metric import Metric
from datetime import datetime, timedelta

async def aggregate_last_window(window_seconds: int = 30):
    async with async_session() as session:
        since = datetime.utcnow() - timedelta(seconds=window_seconds)
        stmt = (
            select(
                Metric.service_name,
                Metric.metric_name,
                func.avg(Metric.value).label("avg_value"),
                func.min(Metric.value).label("min_value"),
                func.max(Metric.value).label("max_value"),
                func.count(Metric.value).label("count")
            )
            .where(Metric.timestamp >= since)
            .group_by(Metric.service_name, Metric.metric_name)
        )
        result = await session.execute(stmt)
        rows = result.fetchall()
        # Можно вернуть список или отправлять по одному — зависит от UI
        return [dict(r._mapping) for r in rows]
