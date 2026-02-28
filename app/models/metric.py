from sqlalchemy import Column, Integer, Float, String, DateTime, func, JSON
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

    # Индекс для ускорения поиска по тегам
    __table_args__ = {
        'postgresql_using': 'gin',
        'postgresql_ops': {'tags': 'jsonb_path_ops'}
    }
