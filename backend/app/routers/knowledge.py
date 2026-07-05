"""База знаний EFFEСOM (6.4, 11.9 ТЗ)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import KnowledgeBaseItem, Role, User
from ..schemas import KnowledgeCreate, KnowledgeOut, KnowledgeUpdate
from ..security import client_ip, get_current_user, require_roles

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

can_edit = require_roles(Role.editor, Role.content_manager)


@router.get("", response_model=list[KnowledgeOut])
def list_items(db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    return db.scalars(select(KnowledgeBaseItem).order_by(KnowledgeBaseItem.id.desc())).all()


@router.post("", response_model=KnowledgeOut, status_code=201)
def create_item(data: KnowledgeCreate, request: Request,
                db: Session = Depends(get_db), user: User = Depends(can_edit)):
    item = KnowledgeBaseItem(**data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    log_action(db, user=user, action="create", entity="knowledge", entity_id=item.id,
               detail=f"Добавлен элемент базы знаний «{item.title}»", ip=client_ip(request))
    return item


@router.put("/{item_id}", response_model=KnowledgeOut)
def update_item(item_id: int, data: KnowledgeUpdate, request: Request,
                db: Session = Depends(get_db), user: User = Depends(can_edit)):
    item = db.get(KnowledgeBaseItem, item_id)
    if item is None:
        raise HTTPException(404, "Элемент не найден")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    log_action(db, user=user, action="update", entity="knowledge", entity_id=item.id,
               detail=f"Изменён элемент «{item.title}»", ip=client_ip(request))
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, request: Request,
                db: Session = Depends(get_db),
                user: User = Depends(require_roles())):
    item = db.get(KnowledgeBaseItem, item_id)
    if item is None:
        raise HTTPException(404, "Элемент не найден")
    title = item.title
    db.delete(item)
    db.commit()
    log_action(db, user=user, action="delete", entity="knowledge", entity_id=item_id,
               detail=f"Удалён элемент «{title}»", ip=client_ip(request))
