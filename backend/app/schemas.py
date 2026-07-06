"""Pydantic-схемы. Валидация всех входящих данных — требование 14.3.1 ТЗ."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import (ArticleStatus, Importance, InfoEventStatus, KnowledgeType,
                     PublicationStatus, Role, SourceStatus, SourceType,
                     TopicStatus, VersionChannel, VersionStatus)


# ------------------------------------------------------------------ auth
class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ------------------------------------------------------------------ users
class UserBase(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    role: Role = Role.editor
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(min_length=10, max_length=200)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=200)


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    last_login_at: datetime | None = None
    created_at: datetime


# ------------------------------------------------------------------ sources
class SourceBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: SourceType
    url: str | None = Field(default=None, max_length=2000)
    access_rules: str | None = None
    check_frequency: str = Field(default="daily", max_length=50)
    status: SourceStatus = SourceStatus.active
    responsible_id: int | None = None


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    type: SourceType | None = None
    url: str | None = Field(default=None, max_length=2000)
    access_rules: str | None = None
    check_frequency: str | None = Field(default=None, max_length=50)
    status: SourceStatus | None = None
    responsible_id: int | None = None


class SourceOut(SourceBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    last_checked_at: datetime | None = None
    created_at: datetime


# ------------------------------------------------------------------ knowledge base
class KnowledgeBase_(BaseModel):
    type: KnowledgeType
    title: str = Field(min_length=1, max_length=255)
    content: str | None = None
    tags: str | None = Field(default=None, max_length=500)
    is_actual: bool = True
    responsible_id: int | None = None


class KnowledgeCreate(KnowledgeBase_):
    pass


class KnowledgeUpdate(BaseModel):
    type: KnowledgeType | None = None
    title: str | None = Field(default=None, max_length=255)
    content: str | None = None
    tags: str | None = Field(default=None, max_length=500)
    is_actual: bool | None = None
    responsible_id: int | None = None


class KnowledgeOut(KnowledgeBase_):
    model_config = ConfigDict(from_attributes=True)
    id: int
    updated_at: datetime


# ------------------------------------------------------------------ topics
class TopicBase(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    direction: str | None = Field(default=None, max_length=255)
    audience: str | None = Field(default=None, max_length=255)
    intent: str | None = Field(default=None, max_length=255)
    keywords: str | None = None
    channel: str | None = Field(default=None, max_length=100)
    priority: int = Field(default=2, ge=1, le=3)
    status: TopicStatus = TopicStatus.idea
    cta: str | None = Field(default=None, max_length=500)
    source_id: int | None = None
    info_event_id: int | None = None
    responsible_id: int | None = None


class TopicCreate(TopicBase):
    pass


class TopicUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    direction: str | None = Field(default=None, max_length=255)
    audience: str | None = Field(default=None, max_length=255)
    intent: str | None = Field(default=None, max_length=255)
    keywords: str | None = None
    channel: str | None = Field(default=None, max_length=100)
    priority: int | None = Field(default=None, ge=1, le=3)
    status: TopicStatus | None = None
    cta: str | None = Field(default=None, max_length=500)
    source_id: int | None = None
    responsible_id: int | None = None


class TopicOut(TopicBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


# ------------------------------------------------------------------ articles
class ArticleBase(BaseModel):
    topic_id: int | None = None
    channel: str = Field(default="site", max_length=100)
    title: str = Field(min_length=1, max_length=500)
    slug: str | None = Field(default=None, max_length=500)
    seo_title: str | None = Field(default=None, max_length=500)
    seo_description: str | None = Field(default=None, max_length=1000)
    brief: str | None = None
    draft_text: str | None = None
    final_text: str | None = None
    faq: str | None = None
    cta: str | None = Field(default=None, max_length=1000)
    internal_links: str | None = None
    sources_list: str | None = None
    effecom_block: str | None = None
    responsible_id: int | None = None


class ArticleCreate(ArticleBase):
    pass


class ArticleUpdate(BaseModel):
    topic_id: int | None = None
    channel: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=500)
    slug: str | None = Field(default=None, max_length=500)
    seo_title: str | None = Field(default=None, max_length=500)
    seo_description: str | None = Field(default=None, max_length=1000)
    brief: str | None = None
    draft_text: str | None = None
    final_text: str | None = None
    faq: str | None = None
    cta: str | None = Field(default=None, max_length=1000)
    internal_links: str | None = None
    sources_list: str | None = None
    effecom_block: str | None = None
    responsible_id: int | None = None


class ArticleOut(ArticleBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: ArticleStatus
    planned_at: datetime | None = None
    review_deadline: datetime | None = None
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    allowed_transitions: list[ArticleStatus] = []
    checklist_done: int = 0
    checklist_total: int = 0


class StatusChangeIn(BaseModel):
    status: ArticleStatus


# --------------------------------------------------- инфоповоды (11.5, Этап 2)
class InfoEventBase(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    source_id: int | None = None
    direction: str | None = Field(default=None, max_length=255)
    importance: Importance = Importance.medium
    summary: str | None = None
    links: str | None = None
    why_important: str | None = None
    related_services: str | None = None
    suggested_titles: str | None = None
    responsible_id: int | None = None


class InfoEventCreate(InfoEventBase):
    pass


class InfoEventUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    source_id: int | None = None
    direction: str | None = Field(default=None, max_length=255)
    importance: Importance | None = None
    summary: str | None = None
    links: str | None = None
    why_important: str | None = None
    related_services: str | None = None
    suggested_titles: str | None = None
    status: InfoEventStatus | None = None
    responsible_id: int | None = None


class InfoEventOut(InfoEventBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: InfoEventStatus
    detected_at: datetime
    created_at: datetime


class TopicFromEventIn(BaseModel):
    """Создание темы из инфоповода за 1-2 клика (11.15.1).
    Все поля необязательны — по умолчанию берутся из инфоповода."""
    title: str | None = Field(default=None, max_length=500)
    direction: str | None = Field(default=None, max_length=255)
    audience: str | None = Field(default=None, max_length=255)
    keywords: str | None = None
    channel: str | None = Field(default=None, max_length=100)
    priority: int = Field(default=2, ge=1, le=3)


# --------------------------------------- версии по каналам (6.8, 11.7, Этап 2)
class VersionUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    body: str | None = None
    status: VersionStatus | None = None


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    article_id: int
    channel: VersionChannel
    title: str | None
    body: str | None
    status: VersionStatus
    published_at: datetime | None
    updated_at: datetime


# --------------------------------------------- чек-лист качества (6.9, Этап 2)
class ChecklistItemUpdate(BaseModel):
    is_done: bool | None = None
    comment: str | None = Field(default=None, max_length=1000)


class ChecklistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    key: str
    label: str
    is_done: bool
    comment: str | None
    updated_by: str | None
    updated_at: datetime


# ------------------------------------------------- комментарии (11.7, Этап 2)
class CommentCreate(BaseModel):
    text: str = Field(min_length=1, max_length=10000)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    author_id: int | None
    author_name: str
    author_role: str | None
    text: str
    created_at: datetime


# --------------------------------------------------- календарь (11.8, Этап 2)
class ScheduleIn(BaseModel):
    planned_at: datetime
    review_deadline: datetime | None = None


class MarkPublishedIn(BaseModel):
    published_at: datetime | None = None


# --------------------------------------------- Этап 4: лог публикаций (6.10)
class PublishIn(BaseModel):
    """Ручная фиксация факта публикации по каналу. Без внешних вызовов."""
    channel: VersionChannel
    publication_url: str | None = Field(default=None, max_length=1000)
    published_at: datetime | None = None
    status: PublicationStatus = PublicationStatus.published
    error_log: str | None = Field(default=None, max_length=5000)


class PublicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    article_id: int
    article_version_id: int | None
    channel: VersionChannel
    publication_url: str | None
    status: PublicationStatus
    error_log: str | None
    published_at: datetime | None
    created_at: datetime


# ------------------------------------------------------------------ audit
class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_email: str | None
    action: str
    entity: str | None
    entity_id: int | None
    detail: str | None
    ip: str | None
    created_at: datetime

# --------------------------------------------------- AI и промпты (Этап 3)
class AIActionIn(BaseModel):
    """Подтверждение перезаписи существующего содержимого (правило 9)."""
    overwrite: bool = False


class PromptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    key: str
    name: str
    purpose: str | None
    template: str
    variables: str | None
    version: int
    updated_by: str | None
    updated_at: datetime


class PromptUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    purpose: str | None = Field(default=None, max_length=500)
    template: str | None = Field(default=None, min_length=10, max_length=20000)
    variables: str | None = Field(default=None, max_length=500)


class PromptVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    version: int
    template: str
    author: str | None
    created_at: datetime


class PromptTestIn(BaseModel):
    """Тестовый запуск промпта (11.12.8) на произвольных переменных."""
    variables: dict[str, str] = Field(default_factory=dict)
