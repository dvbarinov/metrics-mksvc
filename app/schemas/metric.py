from pydantic import BaseModel, Field
from datetime import datetime
from typing import List

class MetricCreate(BaseModel):
    service_name: str
    metric_name: str
    value: float

class MetricRead(MetricCreate):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True  # for SQLAlchemy 2.0

class AggregatedMetric(BaseModel):
    service_name: str
    metric_name: str
    avg_value: float
    min_value: float
    max_value: float
    count: int
    window_seconds: int = Field(default=30)
