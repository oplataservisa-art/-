"""Применение миграций Alembic при старте приложения.

Заменяет прежний Base.metadata.create_all: схема теперь версионируется,
и колонки/таблицы новых этапов добавляются в существующую базу без ручного
SQL. Базы, созданные ДО внедрения Alembic (через create_all на Этапе 1
или Этапе 2), распознаются по имеющимся таблицам и «штампуются»
соответствующей ревизией, после чего докатываются до head.
"""
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .database import engine

logger = logging.getLogger("effecom.migrations")

BASE_DIR = Path(__file__).resolve().parent.parent   # каталог backend/


def _alembic_config() -> Config:
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    return cfg


def run_migrations() -> None:
    cfg = _alembic_config()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "alembic_version" not in tables and tables:
        # База существовала до внедрения Alembic — отмечаем текущую ревизию
        if "info_events" in tables:
            logger.info("Найдена база со схемой Этапа 2 без Alembic — stamp 0002")
            command.stamp(cfg, "0002_stage2")
        elif "users" in tables:
            logger.info("Найдена база со схемой Этапа 1 без Alembic — stamp 0001")
            command.stamp(cfg, "0001_stage1")

    command.upgrade(cfg, "head")
    logger.info("Миграции применены (head)")
