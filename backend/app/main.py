"""Точка входа backend.

Безопасность на уровне приложения:
- CORS по allowlist, не «*» (14.3.5);
- безопасные сообщения об ошибках без стек-трейсов (14.3.14);
- healthcheck для мониторинга (14.7.9);
- первичный администратор создаётся из переменных окружения, пароли не в коде.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text

from .config import settings
from .database import SessionLocal, engine
from .migrate import run_migrations
from .models import Role, User
from .routers import (ai, articles, auth, calendar, channels, dashboard,
                      info_events, knowledge, materials, prompts, publications,
                      sources, topics, users)
from .security import hash_password

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("effecom")


def seed_admin() -> None:
    """Создаёт первого администратора, если таблица пользователей пуста."""
    with SessionLocal() as db:
        if db.scalar(select(User).limit(1)) is not None:
            return
        if settings.admin_password in ("", "CHANGE_ME_IN_ENV"):
            logger.warning(
                "ADMIN_PASSWORD не задан — первичный администратор НЕ создан. "
                "Задайте ADMIN_EMAIL/ADMIN_PASSWORD в .env и перезапустите.")
            return
        db.add(User(
            email=settings.admin_email.lower(),
            name=settings.admin_name,
            role=Role.admin,
            password_hash=hash_password(settings.admin_password),
        ))
        db.commit()
        logger.info("Создан первичный администратор %s", settings.admin_email)


def seed_prompts() -> None:
    """Заводит дефолтные промпты (раздел 12 ТЗ) при пустой таблице.
    Дальше они редактируются только из интерфейса с историей версий."""
    from .models import Prompt, PromptVersion
    from .prompts_seed import DEFAULT_PROMPTS
    with SessionLocal() as db:
        # Аддитивный досев: создаются только ОТСУТСТВУЮЩИЕ ключи.
        # Существующие промпты, их тексты и история версий не изменяются.
        existing = set(db.scalars(select(Prompt.key)).all())
        added = 0
        for spec in DEFAULT_PROMPTS:
            if spec["key"] in existing:
                continue
            prompt = Prompt(key=spec["key"], name=spec["name"],
                            purpose=spec.get("purpose"),
                            template=spec["template"],
                            variables=spec.get("variables"), version=1,
                            updated_by="система (сид)")
            db.add(prompt)
            db.flush()
            db.add(PromptVersion(prompt_id=prompt.id, version=1,
                                 template=spec["template"],
                                 author="система (сид)"))
            added += 1
        if added:
            db.commit()
            logger.info("Досеяны отсутствующие промпты: %d шт.", added)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Схема версионируется через Alembic (backend/migrations); при старте
    # база автоматически докатывается до актуальной ревизии.
    run_migrations()
    seed_admin()
    seed_prompts()
    yield


app = FastAPI(
    title="EFFEСOM Content Service",
    version="0.4.0 (Этап 4a)",
    lifespan=lifespan,
    # В production скрываем интерактивную документацию
    docs_url="/api/docs" if settings.environment != "production" else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.environment != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Внутренние ошибки — в лог; пользователю — безопасное сообщение (14.3.14)."""
    logger.exception("Необработанная ошибка на %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500,
                        content={"detail": "Внутренняя ошибка сервиса"})


@app.get("/api/health")
def health():
    """Healthcheck backend и базы (14.7.9)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        logger.exception("Healthcheck: база недоступна")
        db_ok = False
    status = "ok" if db_ok else "degraded"
    return {"status": status, "database": "ok" if db_ok else "error"}


for router in (auth.router, users.router, sources.router, knowledge.router,
               topics.router, info_events.router, articles.router,
               calendar.router, dashboard.router, ai.router, prompts.router,
               materials.router, publications.router, channels.router):
    app.include_router(router)
