"""Окружение Alembic.

URL базы берётся из настроек приложения (переменная DATABASE_URL),
метаданные — из app.models, поэтому `alembic revision --autogenerate`
видит все модели.
"""
import os
import sys

from alembic import context
from sqlalchemy import create_engine, pool

# Каталог backend/ в sys.path, чтобы импортировался пакет app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings          # noqa: E402
from app.database import Base            # noqa: E402
from app import models                   # noqa: E402,F401  (регистрирует таблицы)

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(settings.database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection,
                          target_metadata=target_metadata,
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
