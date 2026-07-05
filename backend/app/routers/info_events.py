"""Инфоповоды (11.5 ТЗ, Этап 2).

На Этапе 2 инфоповоды заводятся вручную; на Этапе 3 их будет предлагать
модуль мониторинга источников. Ключевое требование 11.15.1 — создать тему
из инфоповода за 1-2 клика: POST /{id}/create-topic.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import (Importance, InfoEvent, InfoEventStatus, Role, Source,
                      Topic, TopicStatus, User)
from ..schemas import (InfoEventCreate, InfoEventOut, InfoEventUpdate,
                       TopicFromEventIn, TopicOut)
from ..security import client_ip, get_current_user, require_roles

router = APIRouter(prefix="/api/info-events", tags=["info-events"])

can_edit = require_roles(Role.editor)


@router.get("", response_model=list[InfoEventOut])
def list_events(status: InfoEventStatus | None = Query(default=None),
                importance: Importance | None = Query(default=None),
                direction: str | None = Query(default=None, max_length=255),
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    query = select(InfoEvent).order_by(InfoEvent.detected_at.desc())
    if status is not None:
        query = query.where(InfoEvent.status == status)
    if importance is not None:
        query = query.where(InfoEvent.importance == importance)
    if direction:
        query = query.where(InfoEvent.direction.ilike(f"%{direction}%"))
    return db.scalars(query).all()


@router.get("/{event_id}", response_model=InfoEventOut)
def get_event(event_id: int, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    event = db.get(InfoEvent, event_id)
    if event is None:
        raise HTTPException(404, "Инфоповод не найден")
    return event


@router.post("", response_model=InfoEventOut, status_code=201)
def create_event(data: InfoEventCreate, request: Request,
                 db: Session = Depends(get_db), user: User = Depends(can_edit)):
    if data.source_id and db.get(Source, data.source_id) is None:
        raise HTTPException(400, "Указанный источник не существует")
    event = InfoEvent(**data.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    log_action(db, user=user, action="create", entity="info_event", entity_id=event.id,
               detail=f"Добавлен инфоповод «{event.title}»", ip=client_ip(request))
    return event


@router.put("/{event_id}", response_model=InfoEventOut)
def update_event(event_id: int, data: InfoEventUpdate, request: Request,
                 db: Session = Depends(get_db), user: User = Depends(can_edit)):
    event = db.get(InfoEvent, event_id)
    if event is None:
        raise HTTPException(404, "Инфоповод не найден")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    db.commit()
    db.refresh(event)
    log_action(db, user=user, action="update", entity="info_event", entity_id=event.id,
               detail=f"Изменён инфоповод «{event.title}»", ip=client_ip(request))
    return event


@router.post("/{event_id}/create-topic", response_model=TopicOut, status_code=201)
def create_topic_from_event(event_id: int, data: TopicFromEventIn, request: Request,
                            db: Session = Depends(get_db),
                            user: User = Depends(can_edit)):
    """Тема из инфоповода за 1-2 клика (11.15.1). Поля можно не передавать —
    возьмутся из инфоповода."""
    event = db.get(InfoEvent, event_id)
    if event is None:
        raise HTTPException(404, "Инфоповод не найден")
    if event.status == InfoEventStatus.rejected:
        raise HTTPException(409, "Инфоповод отклонён — сначала верните его в работу")

    topic = Topic(
        title=data.title or event.title,
        direction=data.direction or event.direction,
        audience=data.audience,
        keywords=data.keywords,
        channel=data.channel,
        priority=data.priority,
        status=TopicStatus.idea,
        source_id=event.source_id,
        info_event_id=event.id,
        responsible_id=user.id,
    )
    db.add(topic)
    event.status = InfoEventStatus.topic_created
    db.commit()
    db.refresh(topic)
    log_action(db, user=user, action="create", entity="topic", entity_id=topic.id,
               detail=f"Тема «{topic.title}» создана из инфоповода №{event.id}",
               ip=client_ip(request))
    return topic


@router.post("/{event_id}/reject", response_model=InfoEventOut)
def reject_event(event_id: int, request: Request,
                 db: Session = Depends(get_db), user: User = Depends(can_edit)):
    event = db.get(InfoEvent, event_id)
    if event is None:
        raise HTTPException(404, "Инфоповод не найден")
    event.status = InfoEventStatus.rejected
    db.commit()
    db.refresh(event)
    log_action(db, user=user, action="status_change", entity="info_event",
               entity_id=event.id, detail=f"Инфоповод «{event.title}» отклонён",
               ip=client_ip(request))
    return event


@router.delete("/{event_id}", status_code=204)
def delete_event(event_id: int, request: Request,
                 db: Session = Depends(get_db),
                 user: User = Depends(require_roles())):  # только admin
    event = db.get(InfoEvent, event_id)
    if event is None:
        raise HTTPException(404, "Инфоповод не найден")
    title = event.title
    db.delete(event)
    db.commit()
    log_action(db, user=user, action="delete", entity="info_event", entity_id=event_id,
               detail=f"Удалён инфоповод «{title}»", ip=client_ip(request))
