from pydantic import BaseModel, Field, RootModel, field_validator, ConfigDict
from datetime import datetime
from typing import Dict, List, Optional, Any

# --- Root Model для тегов (Pydantic v2) ---
# Вместо class TagsField(BaseModel): __root__: Dict...
class TagsField(RootModel[Dict[str, str]]):
    root: Dict[str, str]

    @field_validator('root')
    @classmethod
    def validate_tags(cls, v: Dict[str, str]) -> Dict[str, str]:
        if not isinstance(v, dict):
            raise ValueError("Tags must be a dictionary")
        for key, value in v.items():
            if not key or not value:
                raise ValueError("Tag keys and values cannot be empty")
            if len(key) > 64 or len(str(value)) > 256:
                raise ValueError("Tag key/value too long")
        return v

# --- Основные схемы ---

class MetricCreate(BaseModel):
    service_name: str = Field(..., min_length=1, max_length=128, description="Имя сервиса")
    metric_name: str = Field(..., min_length=1, max_length=128, description="Имя метрики")
    value: float = Field(..., gt=-1e9, lt=1e9, description="Значение метрики")
    tags: Dict[str, str] = Field(default_factory=dict, description="Теги метрики")

    @field_validator('tags')
    @classmethod
    def validate_tags_dict(cls, v: Dict[str, str]) -> Dict[str, str]:
        if not isinstance(v, dict):
            raise ValueError("Tags must be a dictionary")
        for key, value in v.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError("Tag keys and values must be strings")
            if len(key) > 64 or len(value) > 256:
                raise ValueError("Tag key/value too long")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "service_name": "api-gateway",
                "metric_name": "latency_ms",
                "value": 45.6,
                "tags": {
                    "region": "eu-west",
                    "version": "v2.3.1",
                    "env": "production"
                }
            }
        }
    )

class MetricRead(MetricCreate):
    id: int
    timestamp: datetime

    model_config = ConfigDict(
        from_attributes=True  # Аналог orm_mode в Pydantic v2
    )

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
