from sqlalchemy import select, func, ColumnElement
from sqlalchemy.exc import ProgrammingError
from app.core.db import async_session_maker
from app.models.metric import Metric
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


async def aggregate_last_window(
        window_seconds: int = 30,
        group_by_tags: Optional[List[str]] = None,
        filter_tags: Optional[Dict[str, str]] = None
) -> List[Dict]:
    """
    Агрегирует метрики за последние N секунд.
    Корректно обрабатывает GROUP BY для JSONB-тегов.
    """
    try:
        async with async_session_maker() as session:
            since = datetime.utcnow() - timedelta(seconds=window_seconds)

            # Базовые колонки (всегда присутствуют)
            base_columns = [
                Metric.service_name.label("service_name"),
                Metric.metric_name.label("metric_name"),
                func.avg(Metric.value).label("avg_value"),
                func.min(Metric.value).label("min_value"),
                func.max(Metric.value).label("max_value"),
                func.count(Metric.value).label("count"),
                func.percentile_cont(0.5).within_group(Metric.value.asc()).label("p50"),
                func.percentile_cont(0.95).within_group(Metric.value.asc()).label("p95"),
                func.percentile_cont(0.99).within_group(Metric.value.asc()).label("p99")
            ]

            # Базовая группировка
            group_by_cols = [Metric.service_name, Metric.metric_name]

            # Колонки для SELECT и GROUP BY (будут добавлены теги если нужно)
            select_columns = list(base_columns)

            # Обработка тегов для группировки
            tag_expressions: Dict[str, ColumnElement] = {}

            if group_by_tags:
                for tag_key in group_by_tags:
                    # Создаём выражение извлечения тега ОДИН РАЗ
                    tag_expr = Metric.tags[tag_key].astext
                    tag_label = f"tag_{tag_key}"

                    # Добавляем в SELECT с лейблом
                    select_columns.append(tag_expr.label(tag_label))

                    # Сохраняем выражение для GROUP BY
                    tag_expressions[tag_key] = tag_expr

                    # Добавляем то же выражение в GROUP BY
                    group_by_cols.append(tag_expr)

            # Строим базовый запрос
            query = select(*select_columns).where(Metric.timestamp >= since)

            # Применяем фильтрацию по тегам
            if filter_tags:
                for key, value in filter_tags.items():
                    query = query.where(Metric.tags[key].astext == value)

            # Добавляем GROUP BY
            query = query.group_by(*group_by_cols).order_by(
                Metric.service_name,
                Metric.metric_name
            )

            # Выполняем запрос
            result = await session.execute(query)
            rows = result.fetchall()

            # Формируем результат
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

                # Извлекаем значения тегов из результата
                if group_by_tags:
                    for tag_key in group_by_tags:
                        tag_label = f"tag_{tag_key}"
                        tag_value = getattr(row, tag_label, None)
                        if tag_value is not None:
                            agg["tags"][tag_key] = tag_value

                aggregates.append(agg)

            return aggregates

    except ProgrammingError as e:
        error_str = str(e).lower()
        if "groupingerror" in error_str or "must appear in the group by" in error_str:
            logger.warning(f"⚠️ GROUP BY error (check aggregators.py): {e}")
            return []
        logger.error(f"❌ Database error in aggregator: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ Unexpected error in aggregator: {e}", exc_info=True)
        return []
