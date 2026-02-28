from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.dialects.postgresql import JSONB
from app.core.db import get_session
from app.models.metric import Metric
from app.schemas.metric import MetricCreate, MetricRead, HistoryQuery
from datetime import datetime, timedelta
from typing import Optional
import json

router = APIRouter()


@router.post("/", response_model=MetricRead, status_code=201)
async def ingest_metric(
        metric: MetricCreate,
        session: AsyncSession = Depends(get_session)
):
    """Приём метрики с тегами"""
    db_metric = Metric(**metric.model_dump())
    session.add(db_metric)
    await session.commit()
    await session.refresh(db_metric)
    return db_metric


def build_tags_filter(query, model_class, tags_filter: dict):
    """Динамически строит WHERE условия для фильтрации по тегам"""
    for key, value in tags_filter.items():
        query = query.where(model_class.tags[key].astext == value)
    return query


@router.get("/history", response_model=list[MetricRead])
async def get_history(
        service_name: str = Query(..., description="Имя сервиса"),
        metric_name: str = Query(..., description="Имя метрики"),
        tags_filter: Optional[str] = Query(
            None,
            description="JSON-фильтр тегов: ?tags_filter={\"region\":\"eu-west\",\"env\":\"prod\"}"
        ),
        last_minutes: int = Query(60, ge=1, le=1440, description="Период в минутах"),
        session: AsyncSession = Depends(get_session)
):
    """Получение истории метрик с опциональной фильтрацией по тегам"""
    since = datetime.utcnow() - timedelta(minutes=last_minutes)

    query = select(Metric).where(
        Metric.service_name == service_name,
        Metric.metric_name == metric_name,
        Metric.timestamp >= since
    ).order_by(Metric.timestamp)

    # Фильтрация по тегам
    if tags_filter:
        try:
            tags_dict = json.loads(tags_filter)
            query = build_tags_filter(query, Metric, tags_dict)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid tags_filter JSON")

    result = await session.execute(query)
    return result.scalars().all()


@router.get("/unique-tags", response_model=Dict[str, List[str]])
async def get_unique_tags(
        service_name: Optional[str] = None,
        metric_name: Optional[str] = None,
        session: AsyncSession = Depends(get_session)
):
    """Получение всех уникальных тегов и их значений для автокомплита"""
    query = select(Metric.tags)

    if service_name:
        query = query.where(Metric.service_name == service_name)
    if metric_name:
        query = query.where(Metric.metric_name == metric_name)

    result = await session.execute(query)
    all_tags = result.scalars().all()

    # Агрегируем уникальные ключи и значения
    unique = {}
    for tag_dict in all_tags:
        if not tag_dict:
            continue
        for key, value in tag_dict.items():
            if key not in unique:
                unique[key] = set()
            unique[key].add(value)

    return {k: sorted(v) for k, v in unique.items()}
