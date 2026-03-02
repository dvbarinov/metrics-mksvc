from app.models.metric import Metric  # noqa: F401

# Экспортируйте все модели здесь, чтобы Alembic их видел
# Это важно для авто-генерации миграций

__all__ = ["Metric"]