"""Календарь публикаций (11.8 ТЗ, Этап 2).

Отдаёт статьи с плановой или фактической датой публикации за период.
Быстрые действия календаря (запланировать / перенести / отметить
опубликованной) реализованы в routers/articles.py.
"""
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Article, User
from ..security import get_current_user

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

MAX_RANGE_DAYS = 120


@router.get("")
def calendar(date_from: date = Query(...),
             date_to: date = Query(...),
             db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    if date_to < date_from:
        raise HTTPException(400, "date_to раньше date_from")
    if (date_to - date_from).days > MAX_RANGE_DAYS:
        raise HTTPException(400, f"Период не больше {MAX_RANGE_DAYS} дней")

    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)

    rows = db.scalars(
        select(Article)
        .options(joinedload(Article.topic), joinedload(Article.responsible))
        .where(or_(
            Article.planned_at.between(start, end),
            Article.published_at.between(start, end),
        ))
        .order_by(Article.planned_at, Article.published_at)
    ).unique().all()

    return [{
        "id": a.id,
        "title": a.title,
        "channel": a.channel,
        "status": a.status.value,
        "direction": a.topic.direction if a.topic else None,
        "responsible": a.responsible.name if a.responsible else None,
        "planned_at": a.planned_at,
        "review_deadline": a.review_deadline,
        "published_at": a.published_at,
        # день, в который событие показывается в сетке
        "day": (a.published_at or a.planned_at).date().isoformat()
               if (a.published_at or a.planned_at) else None,
    } for a in rows]
