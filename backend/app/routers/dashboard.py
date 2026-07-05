"""Дашборд (11.3) и журнал безопасности (11.13)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (Article, ArticleStatus, AuditLog, InfoEvent,
                      InfoEventStatus, Source, SourceItem, SourceItemStatus,
                      SourceStatus, Topic, TopicStatus, User)
from ..security import get_current_user, require_roles

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    def count_by(model, column):
        rows = db.execute(select(column, func.count()).group_by(column)).all()
        return {str(value.value if hasattr(value, "value") else value): n
                for value, n in rows}

    articles_by_status = count_by(Article, Article.status)
    topics_by_status = count_by(Topic, Topic.status)
    sources_by_status = count_by(Source, Source.status)
    events_by_status = count_by(InfoEvent, InfoEvent.status)

    return {
        "articles_by_status": articles_by_status,
        "topics_by_status": topics_by_status,
        "sources_by_status": sources_by_status,
        "info_events_by_status": events_by_status,
        "cards": {
            "new_info_events": events_by_status.get(InfoEventStatus.new.value, 0),
            "scheduled": articles_by_status.get(ArticleStatus.scheduled.value, 0),
            # Карточки дашборда из 11.3 (в объёме Этапа 1)
            "topics_need_brief": topics_by_status.get(TopicStatus.needs_brief.value, 0)
                                 + topics_by_status.get(TopicStatus.idea.value, 0),
            "drafts_waiting": articles_by_status.get(ArticleStatus.draft.value, 0)
                              + articles_by_status.get(ArticleStatus.editing.value, 0),
            "expert_review": articles_by_status.get(ArticleStatus.expert_review.value, 0),
            "ready_to_publish": articles_by_status.get(ArticleStatus.ready.value, 0),
            "needs_revision": articles_by_status.get(ArticleStatus.needs_revision.value, 0),
            "sources_error": sources_by_status.get(SourceStatus.error.value, 0),
            # Этап 4a: найденные мониторингом материалы, ждущие решения
            "new_materials": db.scalar(
                select(func.count()).select_from(SourceItem)
                .where(SourceItem.status == SourceItemStatus.new)) or 0,
        },
    }


@router.get("/audit")
def audit_log(limit: int = Query(default=100, ge=1, le=500),
              db: Session = Depends(get_db),
              user: User = Depends(require_roles())):  # только admin
    rows = db.scalars(
        select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    ).all()
    return [{
        "id": r.id, "user_email": r.user_email, "action": r.action,
        "entity": r.entity, "entity_id": r.entity_id, "detail": r.detail,
        "ip": r.ip, "created_at": r.created_at,
    } for r in rows]
