"""Журнал входов и важных действий (14.2.7, 15.4 ТЗ).

В журнал никогда не пишутся пароли, токены и содержимое секретов (14.5.3).
"""
from sqlalchemy.orm import Session

from .models import AuditLog, User


def log_action(db: Session, *, user: User | None, action: str,
               entity: str | None = None, entity_id: int | None = None,
               detail: str | None = None, ip: str | None = None,
               email: str | None = None) -> None:
    db.add(AuditLog(
        user_id=user.id if user else None,
        user_email=(user.email if user else email),
        action=action,
        entity=entity,
        entity_id=entity_id,
        detail=detail,
        ip=ip,
    ))
    db.commit()
