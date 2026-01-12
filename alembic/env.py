import os
import sys
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, create_engine
from alembic import context

# Добавляем родительскую директорию в путь для импорта моделей
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Это нужно для поддержки автогенерации миграций
from database import Base
target_metadata = Base.metadata

# Получаем конфигурацию Alembic
config = context.config

# Настраиваем логирование
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

def get_database_url():
    """Получаем URL базы данных с правильным форматом"""
    # 1. Сначала проверяем переменную окружения DATABASE_URL
    database_url = os.getenv("DATABASE_URL")
    
    # 2. Если нет DATABASE_URL, используем значение из alembic.ini
    if not database_url:
        database_url = config.get_main_option("sqlalchemy.url")
    
    # 3. Для Render: преобразуем postgres:// в postgresql://
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    # 4. Для локальной разработки: по умолчанию SQLite
    if not database_url:
        database_url = "sqlite:///./travel_companion.db"
        print(f"⚠️  DATABASE_URL не установлен, используем SQLite: {database_url}")
    
    print(f"📊 Используем БД: {'PostgreSQL' if 'postgresql' in database_url else 'SQLite'}")
    return database_url

def run_migrations_offline():
    """Запуск миграций в офлайн-режиме"""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # Включаем сравнение типов
        compare_server_default=True,  # Включаем сравнение значений по умолчанию
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Запуск миграций в онлайн-режиме"""
    # Получаем URL БД
    database_url = get_database_url()
    
    # Создаем конфигурацию для движка
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = database_url
    
    # Создаем движок
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # Для SQLite нужно отключить транзакции при изменении схемы
    if "sqlite" in database_url:
        connectable = create_engine(database_url)
    
    with connectable.connect() as connection:
        # Настраиваем контекст
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # ВАЖНО: сравниваем типы столбцов
            compare_server_default=True,  # ВАЖНО: сравниваем значения по умолчанию
            render_as_batch=True if "sqlite" in database_url else False,  # Для SQLite
        )

        with context.begin_transaction():
            context.run_migrations()

# Определяем режим выполнения
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()