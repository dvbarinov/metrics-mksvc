from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.models.metric import Metric
from app.schemas.metric import MetricCreate, MetricRead
from datetime import datetime, timedelta

router = APIRouter()

@router.post("/", response_model=MetricRead)
async def ingest_metric(
    metric: MetricCreate,
    session: AsyncSession = Depends(get_session)
):
    db_metric = Metric(**metric.model_dump())
    session.add(db_metric)
    await session.commit()
    await session.refresh(db_metric)
    return db_metric

@router.get("/history", response_model=list[MetricRead])
async def get_history(
    service_name: str,
    metric_name: str,
    last_minutes: int = 60,
    session: AsyncSession = Depends(get_session)
):
    since = datetime.utcnow() - timedelta(minutes=last_minutes)
    result = await session.execute(
        select(Metric)
        .where(
            Metric.service_name == service_name,
            Metric.metric_name == metric_name,
            Metric.timestamp >= since
        )
        .order_by(Metric.timestamp)
    )
    return result.scalars().all()
