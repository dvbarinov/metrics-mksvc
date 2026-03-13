from prometheus_client import (
    Gauge,
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY
)
from fastapi import Response
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.metric import Metric
from sqlalchemy import select, func
import re

# Кэш метрик для производительности
_metrics_cache = {}
_cache_timestamp = None
_cache_ttl = 10  # секунд


def sanitize_metric_name(name: str) -> str:
    """Приводит имя метрики к формату Prometheus"""
    # Заменяем недопустимые символы на подчёркивания
    name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    # Убираем двойные подчёркивания
    name = re.sub(r'__+', '_', name)
    # Убираем подчёркивания в начале и конце
    name = name.strip('_')
    # Если начинается с цифры - добавляем префикс
    if name and name[0].isdigit():
        name = 'metric_' + name
    return name.lower()


def sanitize_label_name(name: str) -> str:
    """Приводит имя лейбла к формату Prometheus"""
    return sanitize_metric_name(name)


def sanitize_label_value(value: str) -> str:
    """Экранирует значения лейблов"""
    return str(value).replace('\\', '\\\\').replace('\n', '\\n').replace('"', '\\"')


class PrometheusExporter:
    """Экспортер метрик в формате Prometheus"""

    def __init__(self):
        self.metric_families = {}

    async def collect_metrics(self, session: AsyncSession, window_minutes: int = 5):
        """
        Собирает метрики из БД и конвертирует в формат Prometheus

        Args:
            session: AsyncSession SQLAlchemy
            window_minutes: окно для сбора метрик (последние N минут)
        """
        global _metrics_cache, _cache_timestamp

        # Проверяем кэш
        now = datetime.utcnow()
        if _cache_timestamp and (now - _cache_timestamp).total_seconds() < _cache_ttl:
            return _metrics_cache

        since = now - timedelta(minutes=window_minutes)

        # Запрос агрегированных метрик
        query = select(
            Metric.service_name,
            Metric.metric_name,
            Metric.tags,
            func.avg(Metric.value).label('avg_value'),
            func.max(Metric.value).label('max_value'),
            func.min(Metric.value).label('min_value'),
            func.count(Metric.value).label('count'),
            func.percentile_cont(0.5).within_group(Metric.value).label('p50'),
            func.percentile_cont(0.95).within_group(Metric.value).label('p95'),
            func.percentile_cont(0.99).within_group(Metric.value).label('p99')
        ).where(
            Metric.timestamp >= since
        ).group_by(
            Metric.service_name,
            Metric.metric_name,
            Metric.tags
        )

        result = await session.execute(query)
        rows = result.fetchall()

        # Группируем по имени метрики
        metrics_by_name = {}
        for row in rows:
            metric_key = f"{row.service_name}_{row.metric_name}"

            if metric_key not in metrics_by_name:
                metrics_by_name[metric_key] = []

            metrics_by_name[metric_key].append({
                'service_name': row.service_name,
                'metric_name': row.metric_name,
                'tags': row.tags or {},
                'avg_value': float(row.avg_value) if row.avg_value else 0,
                'max_value': float(row.max_value) if row.max_value else 0,
                'min_value': float(row.min_value) if row.min_value else 0,
                'count': row.count,
                'p50': float(row.p50) if row.p50 else None,
                'p95': float(row.p95) if row.p95 else None,
                'p99': float(row.p99) if row.p99 else None,
            })

        _metrics_cache = metrics_by_name
        _cache_timestamp = now

        return metrics_by_name

    def generate_prometheus_metrics(self, metrics_data: Dict) -> str:
        """
        Генерирует строку в формате Prometheus из данных

        Формат:
        # HELP metric_name Описание метрики
        # TYPE metric_name gauge
        metric_name{label1="value1", label2="value2"} value
        """
        lines = []

        for metric_key, metric_instances in metrics_data.items():
            if not metric_instances:
                continue

            # Берём первую метрику для определения структуры
            sample = metric_instances[0]
            base_name = sanitize_metric_name(f"{sample['metric_name']}") # {sample['service_name']}_

            # Определяем тип метрики по имени
            metric_type = self._determine_metric_type(sample['metric_name'])

            # HELP и TYPE
            lines.append(f'# HELP {base_name} Metric from {sample["service_name"]} service')
            lines.append(f'# TYPE {base_name} {metric_type}')

            # Генерируем метрики для каждого экземпляра
            for instance in metric_instances:
                # print("instance", instance)
                # Формируем лейблы из тегов
                labels = {
                    'service': instance['service_name'],
                    **instance['tags']
                }

                # Форматируем лейблы
                label_str = self._format_labels(labels)

                # Генерируем разные варианты метрик
                if metric_type == 'gauge':
                    lines.append(f'{base_name}{{type="avg", {label_str}}} {instance["avg_value"]}')
                    lines.append(f'{base_name}{{type="max", {label_str}}} {instance["max_value"]}')
                    lines.append(f'{base_name}{{type="min", {label_str}}} {instance["min_value"]}')

                    # Перцентили, если есть

                    if instance['p50'] is not None:
                        lines.append(f'{base_name}{{type="p50", {label_str}}} {instance["p50"]}')
                    if instance['p95'] is not None:
                        lines.append(f'{base_name}{{type="p95", {label_str}}} {instance["p95"]}')
                    if instance['p99'] is not None:
                        lines.append(f'{base_name}{{type="p99", {label_str}}} {instance["p99"]}')

                elif metric_type == 'counter':
                    lines.append(f'{base_name}{{type="total", {label_str}}} {instance["count"]}')
                    lines.append(f'{base_name}{{type="avg", {label_str}}} {instance["avg_value"]}')

                elif metric_type == 'histogram':
                    # Базовое значение
                    lines.append(f'{base_name}_sum{{{label_str}}} {instance["avg_value"] * instance["count"]}')
                    lines.append(f'{base_name}_count{{{label_str}}} {instance["count"]}')

                    # Bucket'ы для гистограммы
                    print("ПЕРЦЕНТИЛИ histogram")
                    if instance['p95'] is not None:
                        print('p95', instance['p95'])
                        lines.append(
                            f'{base_name}_bucket{{le="{instance["p95"]}", {label_str}}} {int(instance["count"] * 0.95)}')
                    if instance['p99'] is not None:
                        print('p99', instance['p99'])
                        lines.append(
                            f'{base_name}_bucket{{le="{instance["p99"]}", {label_str}}} {int(instance["count"] * 0.99)}')
                    lines.append(f'{base_name}_bucket{{le="+Inf", {label_str}}} {instance["count"]}')

            lines.append('')  # Пустая строка между метриками

        # Добавляем информацию о здоровье сервиса
        lines.append('# HELP metrics_collector_up Status of the metrics collector')
        lines.append('# TYPE metrics_collector_up gauge')
        lines.append(f'metrics_collector_up 1')

        lines.append('# HELP metrics_collector_last_scrape_timestamp Unix timestamp of the last scrape')
        lines.append('# TYPE metrics_collector_last_scrape_timestamp gauge')
        lines.append(f'metrics_collector_last_scrape_timestamp {datetime.utcnow().timestamp()}')

        return '\n'.join(lines)


    def _determine_metric_type(self, metric_name: str) -> str:
        """Определяет тип метрики по её имени"""
        metric_name_lower = metric_name.lower()

        # Counter - для счётчиков
        if any(keyword in metric_name_lower for keyword in ['count', 'total', 'requests', 'errors']):
            return 'counter'

        # Histogram - для латентностей и времён
        if any(keyword in metric_name_lower for keyword in ['latency', 'duration', 'time', 'response']):
            return 'histogram'

        # По умолчанию - gauge
        return 'gauge'


    def _format_labels(self, labels: Dict[str, str]) -> str:
        """Форматирует лейблы в строку для Prometheus"""
        if not labels:
            return ''

        label_parts = []
        for key, value in labels.items():
            sanitized_key = sanitize_label_name(key)
            sanitized_value = sanitize_label_value(value)
            label_parts.append(f'{sanitized_key}="{sanitized_value}"')

        return ', '.join(label_parts) if label_parts else ''


# Singleton экземпляр
exporter = PrometheusExporter()
