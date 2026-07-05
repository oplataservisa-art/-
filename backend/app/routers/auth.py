"""Авторизация (14.2 ТЗ): вход по email+паролю, лимит попыток, журнал входов."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import log_action
from ..config import settings
from ..database import get_db
from ..models import User
from ..schemas import LoginIn, TokenOut, UserOut
from ..security import (bearer_scheme, client_ip, create_access_token,
                        decode_token, get_current_user, session_age_ok,
                        verify_password)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Единый ответ на неверный email И неверный пароль —
# чтобы нельзя было перебором выяснить, какие email зарегистрированы.
BAD_CREDENTIALS = HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный email или пароль")


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    user = db.scalar(select(User).where(User.email == data.email.lower()))

    if user is None:
        log_action(db, user=None, email=data.email, action="login_failed",
                   detail="Неизвестный email", ip=ip)
        raise BAD_CREDENTIALS

    now = datetime.now(timezone.utc)

    # Блокировка после серии неудачных попыток (14.2.8-9)
    if user.locked_until and user.locked_until > now:
        log_action(db, user=user, action="login_blocked",
                   detail="Учётная запись временно заблокирована", ip=ip)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Слишком много попыток входа. Попробуйте позже.")

    if not user.is_active:
        log_action(db, user=user, action="login_failed", detail="Пользователь отключён", ip=ip)
        raise BAD_CREDENTIALS

    if not verify_password(data.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_login_attempts = 0
        db.commit()
        log_action(db, user=user, action="login_failed", detail="Неверный пароль", ip=ip)
        raise BAD_CREDENTIALS

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()
    log_action(db, user=user, action="login", ip=ip)
    return TokenOut(access_token=create_access_token(user))


@router.post("/refresh", response_model=TokenOut)
def refresh(credentials=Depends(bearer_scheme), db: Session = Depends(get_db)):
    """Скользящее продление сессии: пока пользователь активен, frontend
    обновляет токен до истечения. Момент входа (auth_at) переносится в новый
    токен, поэтому абсолютный предел SESSION_MAX_HOURS обойти нельзя."""
    payload = decode_token(credentials)
    if not session_age_ok(payload):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Сессия достигла максимальной длительности, войдите заново")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь отключён")
    auth_at = datetime.fromtimestamp(int(payload["auth_at"]), tz=timezone.utc)
    return TokenOut(access_token=create_access_token(user, auth_at=auth_at))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/logout")
def logout(request: Request, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    # JWT — stateless; фиксируем выход в журнале, токен фронт удаляет сам.
    log_action(db, user=user, action="logout", ip=client_ip(request))
    return {"ok": True}
