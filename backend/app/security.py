"""Ядро безопасности.

Закрывает требования ТЗ:
- 14.2.2  — хеширование паролей bcrypt;
- 14.2.4  — проверка прав на каждом endpoint (require_roles);
- 14.2.10 — истечение сессии (короткоживущий JWT);
- 11.7    — машина статусов редакционного процесса с правами по ролям.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import ArticleStatus, Role, User

bearer_scheme = HTTPBearer(auto_error=False)


# ------------------------------------------------------------------ пароли
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# ------------------------------------------------------------------ JWT
# Модель сессии (14.2.10): токен живёт access_token_minutes; при активности
# frontend продлевает его через /api/auth/refresh (новый токен сохраняет
# момент входа auth_at); абсолютный предел — session_max_hours, дальше
# только повторный вход.
def create_access_token(user: User, auth_at: datetime | None = None) -> str:
    now = datetime.now(timezone.utc)
    auth_at = auth_at or now
    expire = now + timedelta(minutes=settings.access_token_minutes)
    payload = {"sub": str(user.id), "role": user.role.value,
               "auth_at": int(auth_at.timestamp()), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(credentials: HTTPAuthorizationCredentials | None) -> dict:
    """Проверка подписи и срока токена; единые сообщения об ошибках."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Не авторизован")
    try:
        return jwt.decode(
            credentials.credentials, settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия истекла, войдите заново")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Недействительный токен")


def session_age_ok(payload: dict) -> bool:
    """Абсолютный предел сессии: не дольше session_max_hours с момента входа."""
    auth_at = datetime.fromtimestamp(int(payload.get("auth_at", 0)), tz=timezone.utc)
    return datetime.now(timezone.utc) - auth_at < timedelta(hours=settings.session_max_hours)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_token(credentials)
    if not session_age_ok(payload):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Сессия достигла максимальной длительности, войдите заново")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь отключён")
    return user


def require_roles(*roles: Role):
    """Зависимость: доступ только перечисленным ролям. Админ имеет доступ всегда."""
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role == Role.admin or user.role in roles:
            return user
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для этого действия")
    return checker


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ------------------------------------- машина статусов статьи (11.7 ТЗ)
ARTICLE_TRANSITIONS: dict[ArticleStatus, list[ArticleStatus]] = {
    ArticleStatus.draft:          [ArticleStatus.editing, ArticleStatus.archived],
    ArticleStatus.editing:        [ArticleStatus.expert_review, ArticleStatus.needs_revision, ArticleStatus.archived],
    ArticleStatus.needs_revision: [ArticleStatus.editing, ArticleStatus.archived],
    ArticleStatus.expert_review:  [ArticleStatus.ready, ArticleStatus.needs_revision],
    ArticleStatus.ready:          [ArticleStatus.scheduled, ArticleStatus.published, ArticleStatus.needs_revision, ArticleStatus.archived],
    ArticleStatus.scheduled:      [ArticleStatus.published, ArticleStatus.ready],
    ArticleStatus.published:      [ArticleStatus.archived],
    ArticleStatus.publish_error:  [ArticleStatus.ready, ArticleStatus.archived],
    ArticleStatus.archived:       [ArticleStatus.draft],
}

# Какие переходы разрешены каждой роли (админ — все).
# Редактор готовит статью и планирует, но НЕ подтверждает экспертизу
# и НЕ публикует: отметка «Опубликована» — только контент-менеджер и админ.
ROLE_TRANSITIONS: dict[Role, set[tuple[ArticleStatus, ArticleStatus]]] = {
    Role.editor: {
        (a, b) for a, targets in ARTICLE_TRANSITIONS.items() for b in targets
        if (a, b) not in {
            (ArticleStatus.expert_review, ArticleStatus.ready),
            (ArticleStatus.ready, ArticleStatus.published),
            (ArticleStatus.scheduled, ArticleStatus.published),
        }
    },
    Role.expert: {
        (ArticleStatus.expert_review, ArticleStatus.ready),
        (ArticleStatus.expert_review, ArticleStatus.needs_revision),
    },
    Role.content_manager: {
        (ArticleStatus.ready, ArticleStatus.scheduled),
        (ArticleStatus.ready, ArticleStatus.published),
        (ArticleStatus.scheduled, ArticleStatus.published),
        (ArticleStatus.scheduled, ArticleStatus.ready),
    },
    Role.manager: set(),  # руководитель — только просмотр
}


def allowed_transitions_for(user: User, current: ArticleStatus) -> list[ArticleStatus]:
    targets = ARTICLE_TRANSITIONS.get(current, [])
    if user.role == Role.admin:
        return list(targets)
    allowed = ROLE_TRANSITIONS.get(user.role, set())
    return [t for t in targets if (current, t) in allowed]
