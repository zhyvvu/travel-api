# backend/alembic/env.py
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys

# Добавляем текущую директорию в sys.path для импорта
sys.path.append(os.getcwd())

# Импортируем нашу базу данных
from database import Base
from database import DATABASE_URL

# Получаем конфигурацию Alembic
config = context.config

# Устанавливаем URL базы данных
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Настройка логов
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Целевые метаданные для миграций
target_metadata = Base.metadata

def run_migrations_offline():
    """Запуск миграций в оффлайн режиме."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Запуск миграций в онлайн режиме."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()