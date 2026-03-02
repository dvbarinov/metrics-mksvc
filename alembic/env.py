# alembic/env.py

import asyncio
import os
import sys
if sys.platform == "win32":
    # Форсируем использование pytz на Windows
    try:
        import pytz
        pytz.UTC  # Проверка доступности
    except ImportError:
        pass  # Если pytz нет, Alembic попробует dateutil
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config, create_async_engine

from alembic import context

# --- Добавляем путь к проекту в sys.path ---
# Это нужно, чтобы Alembic видел ваши модели
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# --- Импорт моделей для авто-генерации миграций ---
# Импортируйте ВСЕ модели, которые должны отслеживаться
from app.models.metric import Base  # Base из вашего models/__init__.py или конкретной модели

# --- Alembic Config ---
config = context.config

# --- Настройка логирования ---
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Target metadata для авто-генерации ---
target_metadata = Base.metadata


# --- Функция для получения URL из env или config ---
def get_url() -> str:
    """
    Получает DATABASE_URL из переменных окружения или alembic.ini.
    Поддерживает asyncpg диалект.
    """
    url = os.getenv("DATABASE_URL")
    if url:
        # Убеждаемся, что URL использует asyncpg
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    """
    Запуск миграций в 'offline' режиме.
    Без подключения к БД — генерирует SQL-скрипты.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Опции для PostgreSQL
        render_as_batch=True,  # Для SQLite, но безопасно и для PG
        compare_type=True,  # Сравнивать типы колонок
        compare_server_default=True,  # Сравнивать значения по умолчанию
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """
    Запуск миграций в 'online' режиме с async подключением.
    """
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    # Создаём async engine с правильными настройками пула
    connectable = create_async_engine(
        configuration["sqlalchemy.url"],
        poolclass=pool.NullPool,  # Для миграций не нужен сложный пул
        echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def do_run_migrations(connection: Connection) -> None:
    """
    Синхронная функция, которая выполняется внутри async контекста.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
        compare_server_default=True,
        # PostgreSQL-specific options
        version_table_schema="public",  # Схема для таблицы alembic_version
    )

    with context.begin_transaction():
        context.run_migrations()


# --- Главная точка входа ---
if context.is_offline_mode():
    run_migrations_offline()
else:
    # Запускаем async версию
    asyncio.run(run_migrations_online())