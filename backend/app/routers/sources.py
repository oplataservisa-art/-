"""Источники (6.1 ТЗ). Просмотр — все роли, изменение — администратор и редактор."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import Role, Source, User
from ..schemas import SourceCreate, SourceOut, SourceUpdate
from ..security import client_ip, get_current_user, require_roles

router = APIRouter(prefix="/api/sources", tags=["sources"])

can_edit = require_roles(Role.editor)


@router.get("", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    return db.scalars(select(Source).order_by(Source.id.desc())).all()


@router.get("/{source_id}", response_model=SourceOut)
def get_source(source_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(404, "Источник не найден")
    return source


@router.post("", response_model=SourceOut, status_code=201)
def create_source(data: SourceCreate, request: Request,
                  db: Session = Depends(get_db), user: User = Depends(can_edit)):
    source = Source(**data.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    log_action(db, user=user, action="create", entity="source", entity_id=source.id,
               detail=f"Добавлен источник «{source.name}»", ip=client_ip(request))
    return source


@router.put("/{source_id}", response_model=SourceOut)
def update_source(source_id: int, data: SourceUpdate, request: Request,
                  db: Session = Depends(get_db), user: User = Depends(can_edit)):
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(404, "Источник не найден")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    db.commit()
    db.refresh(source)
    log_action(db, user=user, action="update", entity="source", entity_id=source.id,
               detail=f"Изменён источник «{source.name}»", ip=client_ip(request))
    return source


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: int, request: Request,
                  db: Session = Depends(get_db),
                  user: User = Depends(require_roles())):  # удаление — только admin
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(404, "Источник не найден")
    name = source.name
    db.delete(source)
    db.commit()
    log_action(db, user=user, action="delete", entity="source", entity_id=source_id,
               detail=f"Удалён источник «{name}»", ip=client_ip(request))
