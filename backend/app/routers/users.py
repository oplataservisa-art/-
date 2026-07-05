"""Пользователи — только администратор (14.2.5 ТЗ)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import Role, User
from ..schemas import UserCreate, UserOut, UserUpdate
from ..security import client_ip, hash_password, require_roles

router = APIRouter(prefix="/api/users", tags=["users"],
                   dependencies=[Depends(require_roles())])  # только admin


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.id)).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(data: UserCreate, request: Request,
                db: Session = Depends(get_db),
                admin: User = Depends(require_roles())):
    if db.scalar(select(User).where(User.email == data.email.lower())):
        raise HTTPException(409, "Пользователь с таким email уже существует")
    user = User(
        email=data.email.lower(), name=data.name, role=data.role,
        is_active=data.is_active, password_hash=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_action(db, user=admin, action="create", entity="user", entity_id=user.id,
               detail=f"Создан пользователь {user.email} ({user.role.value})",
               ip=client_ip(request))
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, request: Request,
                db: Session = Depends(get_db),
                admin: User = Depends(require_roles())):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Пользователь не найден")

    if data.name is not None:
        user.name = data.name
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        # Нельзя отключить последнего активного администратора
        if not data.is_active and user.role == Role.admin:
            actives = db.scalars(select(User).where(
                User.role == Role.admin, User.is_active.is_(True), User.id != user.id
            )).all()
            if not actives:
                raise HTTPException(400, "Нельзя отключить последнего администратора")
        user.is_active = data.is_active
    if data.password:
        user.password_hash = hash_password(data.password)

    db.commit()
    db.refresh(user)
    log_action(db, user=admin, action="update", entity="user", entity_id=user.id,
               detail=f"Изменён пользователь {user.email}", ip=client_ip(request))
    return user
