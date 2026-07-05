"""API мониторинга источников (Этап 4a, экраны 11.4-11.5 ТЗ).

Правила этапа:
- инфоповоды создаются ТОЛЬКО по клику человека (никакой автоматики);
- AI — только ручной «Анализ (AI)» конкретного материала; в AI-off
  режиме отвечает 503 «AI не настроен», процесс не ломается;
- «Проверить сейчас» выполняется синхронно с HTTP-таймаутом из .env,
  поэтому интерфейс не зависает на мёртвом источнике;
- старые endpoint'ы Этапов 1-3.2 не изменяются — всё новое здесь.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai import extract_json
from ..audit import log_action
from ..database import get_db
from ..models import (Importance, InfoEvent, Role, Source, SourceCheck,
                      SourceCheckStatus, SourceItem, SourceItemStatus, Topic,
                      TopicSourceItem, TopicStatus, User)
from ..monitor import run_source_check
from ..routers.ai import _require_ai, one_at_a_time, run_prompt, services_context
from ..schemas import InfoEventOut, TopicOut
from ..security import client_ip, get_current_user, require_roles

router = APIRouter(prefix="/api", tags=["monitoring"])

can_manage = require_roles(Role.editor)                    # editor + admin
can_view = require_roles(Role.editor, Role.expert, Role.content_manager, Role.manager)

# Направление по ключевым словам (6.2.3) — обычные правила, без AI
DIRECTION_RULES = [
    ("Пожарная безопасность", ("пожарн", "противопожарн", "мчс")),
    ("Промышленная безопасность", ("промышленн", "опо", "ростехнадзор")),
    ("Безопасность дорожного движения", ("бдд", "дорожн", "перевозк", "транспортн")),
    ("Охрана труда", ("охран труд", "охране труда", "охраны труда", "сиз", "соут",
                      "спецоценк", "несчастн", "гит", "трудов инспекц", "минтруд")),
    ("Обучение и ДПО", ("обучен", "дпо", "переподготовк", "квалификац", "инструктаж")),
]


def guess_direction(*texts: str) -> str | None:
    joined = " ".join(t or "" for t in texts).lower()
    for direction, needles in DIRECTION_RULES:
        if any(n in joined for n in needles):
            return direction
    return None


# ------------------------------------------------------------------ схемы
class SourceItemOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    source_id: int
    title: str
    url: str
    published_at: datetime | None
    collected_at: datetime
    excerpt: str | None
    summary: str | None
    importance: str | None
    relevance_score: int
    status: SourceItemStatus
    info_event_id: int | None


class SourceCheckOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    started_at: datetime
    finished_at: datetime | None
    status: SourceCheckStatus
    found_new: int
    error: str | None
    triggered_by: str | None


class FromItemsIn(BaseModel):
    item_ids: list[int] = Field(min_length=1, max_length=50)
    # Этап 4b: результат ручного AI-анализа группы (предпросмотр), который
    # человек решил сохранить кнопкой «Создать инфоповод с анализом»
    summary: str | None = Field(default=None, max_length=4000)
    why_important: str | None = Field(default=None, max_length=2000)
    importance: str | None = Field(default=None, max_length=10)
    suggested_titles: str | None = Field(default=None, max_length=2000)


class BulkIn(BaseModel):
    item_ids: list[int] = Field(min_length=1, max_length=100)
    action: str = Field(pattern="^(hide|restore|reviewed)$")


class TopicFromItemsIn(BaseModel):
    item_ids: list[int] = Field(min_length=1, max_length=50)
    title: str | None = Field(default=None, max_length=500)


# ------------------------------------------------------------- материалы
@router.get("/source-items", response_model=list[SourceItemOut])
def list_items(status: SourceItemStatus | None = None,
               source_id: int | None = None,
               date_from: datetime | None = None,
               date_to: datetime | None = None,
               min_relevance: int | None = None,
               db: Session = Depends(get_db),
               user: User = Depends(can_view)):
    """Фильтры Этапа 4b — опциональные query-параметры; прежние вызовы
    работают без изменений."""
    query = select(SourceItem).order_by(SourceItem.collected_at.desc()).limit(300)
    if status is not None:
        query = query.where(SourceItem.status == status)
    if source_id is not None:
        query = query.where(SourceItem.source_id == source_id)
    if date_from is not None:
        query = query.where(SourceItem.collected_at >= date_from)
    if date_to is not None:
        query = query.where(SourceItem.collected_at <= date_to)
    if min_relevance is not None:
        query = query.where(SourceItem.relevance_score >= min_relevance)
    return db.scalars(query).all()


@router.get("/sources/{source_id}/items", response_model=list[SourceItemOut])
def source_items(source_id: int, db: Session = Depends(get_db),
                 user: User = Depends(can_view)):
    return db.scalars(select(SourceItem)
                      .where(SourceItem.source_id == source_id)
                      .order_by(SourceItem.collected_at.desc()).limit(300)).all()


@router.get("/sources/{source_id}/checks", response_model=list[SourceCheckOut])
def source_checks(source_id: int, db: Session = Depends(get_db),
                  user: User = Depends(can_view)):
    return db.scalars(select(SourceCheck)
                      .where(SourceCheck.source_id == source_id)
                      .order_by(SourceCheck.started_at.desc()).limit(50)).all()


@router.get("/sources-stats")
def sources_stats(db: Session = Depends(get_db), user: User = Depends(can_view)):
    """Агрегаты для новых колонок экрана источников (11.4): найдено новых
    материалов и ошибок за 7 дней. Отдельным endpoint'ом, чтобы не менять
    существующий GET /api/sources."""
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    new_counts = dict(db.execute(
        select(SourceItem.source_id, func.count())
        .where(SourceItem.status == SourceItemStatus.new)
        .group_by(SourceItem.source_id)).all())
    error_counts = dict(db.execute(
        select(SourceCheck.source_id, func.count())
        .where(SourceCheck.started_at >= week_ago,
               SourceCheck.status != SourceCheckStatus.ok)
        .group_by(SourceCheck.source_id)).all())
    ids = set(new_counts) | set(error_counts)
    return {str(i): {"new_items": new_counts.get(i, 0),
                     "errors_7d": error_counts.get(i, 0)} for i in ids}


# ------------------------------------------------------ «Проверить сейчас»
@router.post("/sources/{source_id}/check-now", response_model=SourceCheckOut)
def check_now(source_id: int, request: Request,
              db: Session = Depends(get_db), user: User = Depends(can_manage)):
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(404, "Источник не найден")
    try:
        check = run_source_check(db, source, triggered_by="manual")
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    log_action(db, user=user, action="source_check", entity="source",
               entity_id=source.id,
               detail=f"Проверка вручную: {check.status.value}, новых {check.found_new}",
               ip=client_ip(request))
    return check


# --------------------------------------------- инфоповод из материала(ов)
def _links_block(items: list[SourceItem]) -> str:
    return "\n".join(i.url for i in items)


@router.post("/source-items/{item_id}/info-event", response_model=InfoEventOut,
             status_code=201)
def info_event_from_item(item_id: int, request: Request,
                         db: Session = Depends(get_db),
                         user: User = Depends(can_manage)):
    """Инфоповод из одного материала — без AI: заголовок, ссылка, дата
    и выдержка переносятся кодом. Создаётся только по клику."""
    item = db.get(SourceItem, item_id)
    if item is None:
        raise HTTPException(404, "Материал не найден")
    if item.status == SourceItemStatus.info_event_created and item.info_event_id:
        raise HTTPException(409, "Из этого материала инфоповод уже создан")

    event = InfoEvent(title=item.title, source_id=item.source_id,
                      summary=item.summary or item.excerpt,
                      links=item.url, detected_at=item.published_at or item.collected_at)
    db.add(event)
    db.flush()
    item.status = SourceItemStatus.info_event_created
    item.info_event_id = event.id
    db.commit()
    db.refresh(event)
    log_action(db, user=user, action="create", entity="info_event",
               entity_id=event.id,
               detail=f"Инфоповод из найденного материала №{item.id}",
               ip=client_ip(request))
    return event


@router.post("/info-events/from-items", response_model=InfoEventOut, status_code=201)
def info_event_from_items(data: FromItemsIn, request: Request,
                          db: Session = Depends(get_db),
                          user: User = Depends(can_manage)):
    """Один инфоповод из нескольких выбранных материалов (карточка источника,
    11.4 «Создать тему из выбранных» через путь материалы→инфоповод→тема)."""
    items = db.scalars(select(SourceItem)
                       .where(SourceItem.id.in_(data.item_ids))).all()
    if not items:
        raise HTTPException(404, "Материалы не найдены")
    # Защита от неполного набора: инфоповод создаётся только если найдены ВСЕ id
    missing = set(data.item_ids) - {i.id for i in items}
    if missing:
        raise HTTPException(404, "Часть выбранных материалов не найдена "
                                 f"(id: {', '.join(map(str, sorted(missing)))}) — "
                                 "инфоповод не создан, обновите список")
    # Защита от дублей: у материала уже есть инфоповод — связь не перезаписываем
    used = [i for i in items
            if i.status == SourceItemStatus.info_event_created or i.info_event_id]
    if used:
        titles = "; ".join(f"«{i.title[:80]}» → инфоповод №{i.info_event_id}" for i in used[:5])
        raise HTTPException(409, "Из части материалов инфоповод уже создан: "
                                 f"{titles}. Снимите их с выбора и повторите.")
    lead = items[0]
    importance = None
    if data.importance in ("high", "medium", "low"):
        importance = Importance(data.importance)
    event = InfoEvent(
        title=lead.title, source_id=lead.source_id,
        direction=guess_direction(*[f"{i.title} {i.excerpt or ''}" for i in items]),
        summary=(data.summary or
                 "\n\n".join(f"• {i.title}" + (f" — {i.excerpt}" if i.excerpt else "")
                             for i in items))[:4000],
        links=_links_block(items),
        why_important=data.why_important,
        suggested_titles=data.suggested_titles,
        importance=importance or Importance.medium,
        detected_at=min((i.published_at or i.collected_at) for i in items))
    db.add(event)
    db.flush()
    for item in items:
        item.status = SourceItemStatus.info_event_created
        item.info_event_id = event.id
    db.commit()
    db.refresh(event)
    log_action(db, user=user, action="create", entity="info_event",
               entity_id=event.id,
               detail=f"Инфоповод из {len(items)} найденных материалов",
               ip=client_ip(request))
    return event


# ------------------------------------------------------------------ скрыть
@router.post("/source-items/{item_id}/hide", response_model=SourceItemOut)
def hide_item(item_id: int, db: Session = Depends(get_db),
              user: User = Depends(can_manage)):
    item = db.get(SourceItem, item_id)
    if item is None:
        raise HTTPException(404, "Материал не найден")
    item.status = SourceItemStatus.hidden
    db.commit()
    db.refresh(item)
    return item


# --------------------------------------------------- ручной «Анализ (AI)»
@router.post("/source-items/{item_id}/analyze", response_model=SourceItemOut)
def analyze_item(item_id: int, request: Request,
                 db: Session = Depends(get_db), user: User = Depends(can_manage)):
    """Единственное применение AI на этапе мониторинга — по явному клику:
    выжимка, важность и «почему важно» для одного материала. Бюджет и
    журнал ai_requests Этапа 3 действуют как обычно."""
    _require_ai()
    item = db.get(SourceItem, item_id)
    if item is None:
        raise HTTPException(404, "Материал не найден")

    source = db.get(Source, item.source_id)
    with one_at_a_time(f"item_analyze:{item_id}"):
        raw = run_prompt(db, user, "source_analysis", {
            "source_name": source.name if source else "",
            "content": f"{item.title}\n{item.url}\n\n{item.excerpt or ''}\n\n"
                       "Верни СТРОГО JSON: {\"summary\": \"выжимка 2-3 предложения\", "
                       "\"importance\": \"high|medium|low\", "
                       "\"why_important\": \"почему важно клиентам EFFEСOM\"}",
        }, kind="item_analysis")
        try:
            payload = extract_json(raw)
            item.summary = str(payload.get("summary") or raw)[:4000]
            importance = str(payload.get("importance") or "").lower()
            item.importance = importance if importance in ("high", "medium", "low") else None
            why = str(payload.get("why_important") or "").strip()
            if why:
                item.summary += f"\n\nПочему важно: {why}"
        except Exception:                                  # noqa: BLE001
            item.summary = raw[:4000]                      # ответ не в JSON — сохраняем как есть
        if item.status == SourceItemStatus.new:
            item.status = SourceItemStatus.reviewed
        db.commit()
        db.refresh(item)
        log_action(db, user=user, action="ai_check", entity="source_item",
                   entity_id=item.id, detail="Ручной AI-анализ материала",
                   ip=client_ip(request))
        return item


# ------------------------------------------------ массовые действия (Этап 4b)
@router.post("/source-items/bulk")
def bulk_action(data: BulkIn, request: Request,
                db: Session = Depends(get_db), user: User = Depends(can_manage)):
    """Скрыть / восстановить / отметить просмотренными — обычные статусы,
    без AI. Материалы с созданным инфоповодом не трогаются."""
    items = db.scalars(select(SourceItem)
                       .where(SourceItem.id.in_(data.item_ids))).all()
    if not items:
        raise HTTPException(404, "Материалы не найдены")
    transitions = {
        "hide": (lambda i: i.status != SourceItemStatus.info_event_created,
                 SourceItemStatus.hidden),
        "restore": (lambda i: i.status == SourceItemStatus.hidden,
                    SourceItemStatus.new),
        "reviewed": (lambda i: i.status == SourceItemStatus.new,
                     SourceItemStatus.reviewed),
    }
    allowed, target = transitions[data.action]
    changed = 0
    for item in items:
        if allowed(item):
            item.status = target
            changed += 1
    db.commit()
    log_action(db, user=user, action="bulk_" + data.action, entity="source_item",
               entity_id=items[0].id,
               detail=f"Массовое действие «{data.action}»: изменено {changed} из {len(items)}",
               ip=client_ip(request))
    return {"changed": changed, "total": len(items)}


# --------------------------------- ручной AI-анализ группы (6.2.4-6.2.6; 4b)
@router.post("/source-items/analyze-group")
def analyze_group(data: TopicFromItemsIn, request: Request,
                  db: Session = Depends(get_db), user: User = Depends(can_manage)):
    """ПРЕДПРОСМОТР: один AI-запрос по группе выбранных материалов.
    Ничего не сохраняет — результат показывается человеку, и только
    отдельный клик «Создать инфоповод с анализом» передаёт его в
    /info-events/from-items. AI-off → 503 «AI не настроен»."""
    _require_ai()
    items = db.scalars(select(SourceItem)
                       .where(SourceItem.id.in_(data.item_ids))).all()
    if not items:
        raise HTTPException(404, "Материалы не найдены")

    materials_block = "\n\n".join(
        f"- {i.title}\n  {i.url}\n  {(i.excerpt or '')[:400]}" for i in items)[:8000]
    lock_key = "group_analyze:" + ",".join(str(i) for i in sorted(data.item_ids)[:10])
    with one_at_a_time(lock_key):
        raw = run_prompt(db, user, "group_analysis",
                         {"materials": materials_block,
                          "services": services_context(db)},
                         kind="group_analysis")
    try:
        payload = extract_json(raw)
        importance = str(payload.get("importance") or "").lower()
        result = {
            "summary": str(payload.get("summary") or "").strip(),
            "why_important": str(payload.get("why_important") or "").strip(),
            "importance": importance if importance in ("high", "medium", "low") else None,
            "suggested_titles": str(payload.get("suggested_titles") or "").strip(),
        }
    except Exception:                                      # noqa: BLE001
        result = {"summary": raw[:4000], "why_important": None,
                  "importance": None, "suggested_titles": None}
    log_action(db, user=user, action="ai_check", entity="source_item",
               entity_id=items[0].id,
               detail=f"AI-анализ группы из {len(items)} материалов (предпросмотр)",
               ip=client_ip(request))
    return {"item_ids": data.item_ids, "items_count": len(items), **result,
            "detail": "Предпросмотр: ничего не сохранено. Сохранение — кнопкой "
                      "«Создать инфоповод с анализом»."}


# ------------------------- тема из выбранных материалов (11.4.7, 11.15.1; 4b)
@router.post("/topics/from-items", response_model=TopicOut, status_code=201)
def topic_from_items(data: TopicFromItemsIn, request: Request,
                     db: Session = Depends(get_db), user: User = Depends(can_manage)):
    """Тема напрямую из материалов, без AI: заголовок — ведущего материала
    (или введённый), направление — по словарю правил, связи материалов —
    в topic_source_items (раздел 9 ТЗ). Путь «инфоповод → тема» не меняется."""
    items = db.scalars(select(SourceItem)
                       .where(SourceItem.id.in_(data.item_ids))).all()
    if not items:
        raise HTTPException(404, "Материалы не найдены")
    lead = items[0]
    topic = Topic(
        title=(data.title or lead.title)[:500],
        direction=guess_direction(*[f"{i.title} {i.excerpt or ''}" for i in items]),
        keywords=", ".join(sorted({w for i in items
                                   for w in _matched_keywords(i)}))[:1000] or None,
        source_id=lead.source_id,
        status=TopicStatus.idea)
    db.add(topic)
    db.flush()
    for item in items:
        db.add(TopicSourceItem(topic_id=topic.id, source_item_id=item.id))
        if item.status == SourceItemStatus.new:
            item.status = SourceItemStatus.reviewed
    db.commit()
    db.refresh(topic)
    log_action(db, user=user, action="create", entity="topic", entity_id=topic.id,
               detail=f"Тема из {len(items)} найденных материалов",
               ip=client_ip(request))
    return topic


def _matched_keywords(item: SourceItem) -> set[str]:
    from ..parsing import RELEVANCE_KEYWORDS
    text = f"{item.title} {item.excerpt or ''}".lower()
    return {kw for kw in RELEVANCE_KEYWORDS if kw in text and len(kw) > 3}


@router.get("/topics/{topic_id}/source-items", response_model=list[SourceItemOut])
def topic_source_items_list(topic_id: int, db: Session = Depends(get_db),
                            user: User = Depends(can_view)):
    """Из каких материалов родилась тема (след для редакции)."""
    ids = db.scalars(select(TopicSourceItem.source_item_id)
                     .where(TopicSourceItem.topic_id == topic_id)).all()
    if not ids:
        return []
    return db.scalars(select(SourceItem).where(SourceItem.id.in_(ids))).all()
