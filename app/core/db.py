import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

# Конфигурация из переменных окружения
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/metrics_db"
)

# Создаем асинхронный движок
# pool_size: количество постоянных соединений в пуле
# max_overflow: количество дополнительных соединений при пиковой нагрузке
engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",  # Логирование SQL
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Проверка соединения перед использованием
    pool_recycle=3600,  # Пересоздание соединения через час
)

# Фабрика сессий
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Базовый класс для моделей
Base = declarative_base()


# Зависимость для внедрения сессии в эндпоинты
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Генератор сессий для зависимости FastAPI.
    Гарантирует закрытие сессии после запроса.
    """
    session = async_session_maker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# Глобальная сессия для фоновых задач (broadcaster)
# В продакшене лучше передавать сессию явно, но для фоновых задач допустим такой паттерн
async def get_db_session_for_background() -> AsyncSession:
    return async_session_maker()


# Контекстный менеджер для удобного использования в скриптах
class DatabaseSession:
    async def __aenter__(self) -> AsyncSession:
        self.session = async_session_maker()
        return self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.session.rollback()
        else:
            await self.session.commit()
        await self.session.close()


async def init_db():
    """Инициализация БД (создание таблиц)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Закрытие соединений при выключении приложения."""
    await engine.dispose()
