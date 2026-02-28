from sqlalchemy import Column, Integer, Float, String, DateTime, func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Metric(Base):
    # Для производительности можно партиционировать таблицу по timestamp
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, index=True)
    service_name = Column(String, index=True)
    metric_name = Column(String, index=True)  # e.g., "latency_ms", "rps"
    value = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

