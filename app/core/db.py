import asyncio
import os
import logging
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool  # Для отладки можно отключить пул

logger = logging.getLogger(__name__)

# Базовый класс для моделей
Base = declarative_base()

# Конфигурация из переменных окружения
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:12345@localhost:5432/metrics_db"
)

# Создаем асинхронный движок
# pool_size: количество постоянных соединений в пуле
# max_overflow: количество дополнительных соединений при пиковой нагрузке
# - engine = create_async_engine(DATABASE_URL, echo=True)
engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",  # Логирование SQL
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,  # Проверка соединения перед использованием
    pool_recycle=300,  # Пересоздание соединения каждые 5 минут # Пересоздание соединения через час
    # poolclass=NullPool,  # Раскомментировать для отладки, если есть проблемы с пулом
)

# Фабрика сессий
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


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


async def check_db_connection() -> bool:
    """Проверка доступности БД при старте."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            logger.info("✅ Database connection successful")
            return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False


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
    try:
        # Проверяем, существует ли таблица
        async with engine.connect() as conn:
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'metrics'
                    );
                """)
            )
            table_exists = result.scalar()

            if table_exists:
                logger.info("✅ Table 'metrics' already exists")
                return

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables created")
    except Exception as e:
        logger.error(f"❌ Failed to create tables: {e}")
        raise


async def close_db():
    """Закрытие соединений при выключении приложения."""
    await engine.dispose()
    logger.info("🔒 Database connections closed")


if __name__ == "__main__":
    asyncio.run(check_db_connection())
