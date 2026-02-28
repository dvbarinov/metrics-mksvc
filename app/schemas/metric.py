from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Dict, List, Optional
from typing_extensions import Annotated

class TagsField(BaseModel):
    """Валидация тегов: ключи и значения — строки, без спецсимволов"""
    __root__: Dict[str, str]

    @field_validator('__root__')
    @classmethod
    def validate_tags(cls, v):
        if not isinstance(v, dict):
            raise ValueError("Tags must be a dictionary")
        for key, value in v.items():
            if not key or not value:
                raise ValueError("Tag keys and values cannot be empty")
            if len(key) > 64 or len(str(value)) > 256:
                raise ValueError("Tag key/value too long")
        return v

class MetricCreate(BaseModel):
    service_name: str = Field(..., min_length=1, max_length=128)
    metric_name: str = Field(..., min_length=1, max_length=128)
    value: float = Field(..., gt=-1e9, lt=1e9)
    tags: Dict[str, str] = Field(default_factory=dict)  # ← теги

    @field_validator('tags')
    @classmethod
    def validate_tags_dict(cls, v):
        if not isinstance(v, dict):
            raise ValueError("Tags must be a dictionary")
        for key, value in v.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError("Tag keys and values must be strings")
            if len(key) > 64 or len(value) > 256:
                raise ValueError("Tag key/value too long")
        return v

class MetricRead(MetricCreate):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True

class AggregatedMetric(BaseModel):
    service_name: str
    metric_name: str
    tags: Dict[str, str] = Field(default_factory=dict)
    avg_value: float
    min_value: float
    max_value: float
    p50: Optional[float] = None
    p95: Optional[float] = None
    p99: Optional[float] = None
    count: int
    window_seconds: int = Field(default=30)

class HistoryQuery(BaseModel):
    service_name: str
    metric_name: str
    tags_filter: Optional[Dict[str, str]] = None
    last_minutes: int = Field(default=60, ge=1, le=1440)
