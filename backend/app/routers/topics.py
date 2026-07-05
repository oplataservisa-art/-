"""Темы (6.5, 11.6 ТЗ)."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import Role, Topic, TopicStatus, User
from ..schemas import TopicCreate, TopicOut, TopicUpdate
from ..security import client_ip, get_current_user, require_roles

router = APIRouter(prefix="/api/topics", tags=["topics"])

can_edit = require_roles(Role.editor)


@router.get("", response_model=list[TopicOut])
def list_topics(status: TopicStatus | None = Query(default=None),
                direction: str | None = Query(default=None, max_length=255),
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    query = select(Topic).order_by(Topic.priority, Topic.id.desc())
    if status is not None:
        query = query.where(Topic.status == status)
    if direction:
        query = query.where(Topic.direction.ilike(f"%{direction}%"))
    return db.scalars(query).all()


@router.get("/{topic_id}", response_model=TopicOut)
def get_topic(topic_id: int, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(404, "Тема не найдена")
    return topic


@router.post("", response_model=TopicOut, status_code=201)
def create_topic(data: TopicCreate, request: Request,
                 db: Session = Depends(get_db), user: User = Depends(can_edit)):
    topic = Topic(**data.model_dump())
    db.add(topic)
    db.commit()
    db.refresh(topic)
    log_action(db, user=user, action="create", entity="topic", entity_id=topic.id,
               detail=f"Создана тема «{topic.title}»", ip=client_ip(request))
    return topic


@router.put("/{topic_id}", response_model=TopicOut)
def update_topic(topic_id: int, data: TopicUpdate, request: Request,
                 db: Session = Depends(get_db), user: User = Depends(can_edit)):
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(404, "Тема не найдена")
    old_status = topic.status
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(topic, field, value)
    db.commit()
    db.refresh(topic)
    detail = f"Изменена тема «{topic.title}»"
    if data.status is not None and data.status != old_status:
        detail += f" (статус: {old_status.value} → {topic.status.value})"
    log_action(db, user=user, action="update", entity="topic", entity_id=topic.id,
               detail=detail, ip=client_ip(request))
    return topic


@router.delete("/{topic_id}", status_code=204)
def delete_topic(topic_id: int, request: Request,
                 db: Session = Depends(get_db),
                 user: User = Depends(require_roles())):
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(404, "Тема не найдена")
    title = topic.title
    db.delete(topic)
    db.commit()
    log_action(db, user=user, action="delete", entity="topic", entity_id=topic_id,
               detail=f"Удалена тема «{title}»", ip=client_ip(request))
