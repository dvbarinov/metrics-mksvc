from sqlalchemy import Column, Integer, Float, String, DateTime, func, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()

class Metric(Base):
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, index=True)
    service_name = Column(String, index=True)
    metric_name = Column(String, index=True)
    value = Column(Float, nullable=False)
    tags = Column(JSONB, nullable=True, default=dict)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # ✅ Правильное создание GIN-индекса для JSONB
    __table_args__ = (
        Index(
            'ix_metrics_tags',
            'tags',
            postgresql_using='gin',
            postgresql_ops={'tags': 'jsonb_path_ops'}
        ),
        # Индекс для быстрых выборок по времени (важно для метрик)
        Index(
            'ix_metrics_timestamp',
            'timestamp',
            postgresql_using='btree'
        ),
        # Композитный индекс для частых запросов
        Index(
            'ix_metrics_service_metric_ts',
            'service_name',
            'metric_name',
            'timestamp',
            postgresql_using='btree'
        ),
    )