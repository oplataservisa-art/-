"""Воркер мониторинга источников (Этап 4a; ТЗ 14.7 — фоновые задачи
изолированы от веб-процесса).

Запуск: python -m app.monitor (отдельный сервис `worker` в docker-compose,
тот же образ, что и backend).

При MONITOR_ENABLED=false (по умолчанию) воркер ничего не парсит —
пишет об этом в лог и спит. Включение — только через .env.

run_source_check() — общая логика одного прогона; её же синхронно
вызывает кнопка «Проверить сейчас» из API. Все таймауты — внутри
app.parsing (HTTP-таймаут обязателен), поэтому зависший источник
не подвешивает ни воркер, ни интерфейс.
"""
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from .config import settings
from .database import SessionLocal
from .models import (Source, SourceCheck, SourceCheckStatus, SourceItem,
                     SourceItemStatus, SourceStatus)
from .parsing import FetchBlocked, FetchError, fetch_url, parse_source, robots_allows

logger = logging.getLogger("effecom.monitor")

FREQUENCY_DELTA = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    # manual — только вручную кнопкой «Проверить сейчас»
}

# Защита от параллельного прогона одного источника РАЗНЫМИ процессами
# (воркер и backend): транзакционный advisory-лок PostgreSQL. Держится до
# конца транзакции и снимается автоматически при commit/rollback — «зависший»
# лок невозможен даже при падении процесса.
ADVISORY_NAMESPACE = 42041  # произвольный класс ключей мониторинга EFFEСOM


def _try_lock_source(db, source_id: int) -> bool:
    return bool(db.scalar(
        text("SELECT pg_try_advisory_xact_lock(:ns, :sid)"),
        {"ns": ADVISORY_NAMESPACE, "sid": source_id}))


def run_source_check(db, source: Source, triggered_by: str) -> SourceCheck:
    """Один прогон источника: robots → загрузка → разбор → дедуп → запись.
    Ничего не создаёт, кроме source_items и source_checks; инфоповоды
    и темы автоматически НЕ создаются — только человек кнопками."""
    if not _try_lock_source(db, source.id):
        raise RuntimeError("Проверка этого источника уже выполняется "
                           "(воркером или другим пользователем) — дождитесь завершения")

    check = SourceCheck(source_id=source.id, triggered_by=triggered_by,
                        started_at=datetime.now(timezone.utc))
    db.add(check)
    try:
        if not source.url:
            raise FetchError("У источника не указан URL")

        if not robots_allows(source.url):
            raise FetchBlocked("robots.txt источника запрещает автоматический доступ")

        body = fetch_url(source.url)
        parsed = parse_source(body, source.url)

        known_urls = set(db.scalars(
            select(SourceItem.url).where(SourceItem.source_id == source.id)).all())
        known_hashes = set(db.scalars(
            select(SourceItem.content_hash).where(SourceItem.source_id == source.id)).all())

        added = 0
        for item in parsed:
            if added >= settings.monitor_max_items_per_run:
                break
            if item.url in known_urls or item.content_hash in known_hashes:
                continue                                   # дедупликация
            db.add(SourceItem(
                source_id=source.id, title=item.title, url=item.url,
                published_at=item.published_at, excerpt=item.excerpt or None,
                relevance_score=item.relevance_score,
                content_hash=item.content_hash,
                status=SourceItemStatus.new))
            known_urls.add(item.url)
            known_hashes.add(item.content_hash)
            added += 1

        check.status = SourceCheckStatus.ok
        check.found_new = added
        source.status = SourceStatus.active
    except FetchBlocked as exc:
        check.status = SourceCheckStatus.blocked
        check.error = str(exc)
        source.status = SourceStatus.error
    except (FetchError, Exception) as exc:  # noqa: BLE001 — прогон не должен ронять воркер
        check.status = SourceCheckStatus.error
        check.error = str(exc)[:2000]
        source.status = SourceStatus.error
    finally:
        check.finished_at = datetime.now(timezone.utc)
        source.last_checked_at = check.finished_at
        try:
            db.commit()                          # здесь же освобождается advisory-лок
        except IntegrityError:
            # Страховка: гонка вставок с параллельным прогоном упёрлась в
            # уникальный индекс (source_id, url). Прогон не падает: фиксируем
            # только запись о проверке, дубли отбрасываются базой.
            db.rollback()
            check = SourceCheck(source_id=source.id, triggered_by=triggered_by,
                                started_at=check.started_at,
                                finished_at=datetime.now(timezone.utc),
                                status=SourceCheckStatus.ok, found_new=0,
                                error="Параллельный прогон уже сохранил эти материалы — "
                                      "дубли отброшены")
            source.last_checked_at = check.finished_at
            db.add(check)
            db.commit()
    return check


def _due_sources(db) -> list[Source]:
    now = datetime.now(timezone.utc)
    due = []
    for source in db.scalars(select(Source).where(Source.status != SourceStatus.paused)):
        delta = FREQUENCY_DELTA.get(
            source.check_frequency.value if hasattr(source.check_frequency, "value")
            else source.check_frequency)
        if delta is None:                                  # manual
            continue
        if source.last_checked_at is None or source.last_checked_at + delta <= now:
            due.append(source)
    return due


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logger.info("Воркер мониторинга запущен (tick=%d c)", settings.monitor_tick_seconds)
    if not settings.monitor_enabled:
        logger.info("MONITOR_ENABLED=false — мониторинг выключен, парсинг не выполняется. "
                    "Включите в .env и перезапустите worker.")
    while True:
        if settings.monitor_enabled:
            try:
                with SessionLocal() as db:
                    due = _due_sources(db)
                    if due:
                        logger.info("К проверке: %d источников", len(due))
                    for source in due:
                        try:
                            check = run_source_check(db, source, triggered_by="worker")
                            logger.info("Источник %s: %s, новых %d",
                                        source.name, check.status.value, check.found_new)
                        except RuntimeError:
                            continue
            except Exception:                              # noqa: BLE001
                logger.exception("Ошибка цикла мониторинга — продолжаю после паузы")
        time.sleep(settings.monitor_tick_seconds)


if __name__ == "__main__":
    main()
