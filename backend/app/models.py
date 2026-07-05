"""Модели БД — Этапы 1-2 (разделы 9-11 ТЗ).

Этап 1: User, Source, KnowledgeBaseItem, Topic, Article, AuditLog.
Этап 4b: TopicSourceItem — связь темы с материалами, из которых она
создана (раздел 9 ТЗ: у Topic есть source_items; старая таблица topics
не изменяется, связь живёт в отдельной join-таблице).
Этап 4a (мониторинг): SourceItem (найденные материалы, сущность из
раздела 9 ТЗ), SourceCheck (история проверок источника, экран 11.4).
Этап 3 (AI-генерация): Prompt/PromptVersion (редактируемые промпты,
разделы 11.12 и 12), AIRequest (журнал расходов AI, 14.11.7-8).
Этап 2 (редакционный процесс): InfoEvent (инфоповоды, 11.5),
ArticleVersion (версии по каналам, 6.8 и 11.7), ArticleChecklistItem
(чек-лист качества, 6.9), ArticleComment (комментарии эксперта, 11.7),
поля планирования публикации у Article (календарь, 11.8).
Сущности этапов 3-5 (парсинг SourceItem, интеграции Publication,
AnalyticsMetric) сознательно НЕ созданы.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import (Boolean, DateTime, Enum, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- Роли (раздел 7)
class Role(str, enum.Enum):
    admin = "admin"                    # Администратор — полный доступ
    editor = "editor"                  # Редактор — темы, статьи, проверки
    expert = "expert"                  # Эксперт — просмотр и подтверждение точности
    content_manager = "content_manager"  # Контент-менеджер — публикации и календарь
    manager = "manager"                # Руководитель — дашборд и отчёты


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))  # bcrypt, 14.2.2
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.editor)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # 14.2.6

    # Защита от подбора пароля (14.2.8-9)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ------------------------------------------------------------- Источники (6.1)
class SourceType(str, enum.Enum):
    official = "official"          # сайты министерств и ведомств
    legal_acts = "legal_acts"      # страницы с нормативными актами
    news = "news"                  # новости и обзоры законодательства
    legal_system = "legal_system"  # КонсультантПлюс/Гарант (легальный доступ)
    effecom = "effecom"            # сайт EFFEСOM и база курсов
    forum = "forum"                # форумы и профсообщества
    rss = "rss"                    # RSS-ленты
    manual = "manual"              # вручную загруженные документы
    competitor = "competitor"      # конкуренты (анализ тем, без копирования)


class SourceStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    error = "error"


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[SourceType] = mapped_column(Enum(SourceType))
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    access_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    check_frequency: Mapped[str] = mapped_column(String(50), default="daily")
    status: Mapped[SourceStatus] = mapped_column(Enum(SourceStatus), default=SourceStatus.active)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    responsible: Mapped[User | None] = relationship()


# ----------------------------------------------------- База знаний EFFEСOM (6.4)
class KnowledgeType(str, enum.Enum):
    course = "course"
    direction = "direction"
    pricing = "pricing"
    documents = "documents"
    faq = "faq"
    advantages = "advantages"
    forbidden_phrases = "forbidden_phrases"
    brand_style = "brand_style"
    legal_limits = "legal_limits"
    other = "other"


class KnowledgeBaseItem(Base):
    __tablename__ = "knowledge_base_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[KnowledgeType] = mapped_column(Enum(KnowledgeType))
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_actual: Mapped[bool] = mapped_column(Boolean, default=True)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    responsible: Mapped[User | None] = relationship()


# ------------------------------------------------------------------ Темы (6.5)
class TopicStatus(str, enum.Enum):
    idea = "idea"                      # Идея
    needs_brief = "needs_brief"        # Нужен бриф
    brief_ready = "brief_ready"        # Бриф готов
    writing = "writing"                # Пишется статья
    article_created = "article_created"  # Статья создана
    rejected = "rejected"              # Отклонена
    archived = "archived"              # Архив


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    direction: Mapped[str | None] = mapped_column(String(255), nullable=True)   # направление обучения
    audience: Mapped[str | None] = mapped_column(String(255), nullable=True)    # целевая аудитория
    intent: Mapped[str | None] = mapped_column(String(255), nullable=True)      # поисковый интент
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str | None] = mapped_column(String(100), nullable=True)     # рекомендуемый канал
    priority: Mapped[int] = mapped_column(Integer, default=2)                   # 1 высокий / 2 средний / 3 низкий
    status: Mapped[TopicStatus] = mapped_column(Enum(TopicStatus), default=TopicStatus.idea)
    cta: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    info_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("info_events.id", ondelete="SET NULL"), nullable=True)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    source: Mapped[Source | None] = relationship()
    responsible: Mapped[User | None] = relationship()


# ----------------------------------------------------------------- Статьи (11.7)
class ArticleStatus(str, enum.Enum):
    draft = "draft"                    # Черновик
    needs_revision = "needs_revision"  # Требует доработки
    editing = "editing"                # На редактуре
    expert_review = "expert_review"    # На экспертной проверке
    ready = "ready"                    # Готова к публикации
    scheduled = "scheduled"            # Запланирована
    published = "published"            # Опубликована
    publish_error = "publish_error"    # Ошибка публикации
    archived = "archived"              # Архив


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(100), default="site")
    title: Mapped[str] = mapped_column(String(500))
    slug: Mapped[str | None] = mapped_column(String(500), nullable=True)
    seo_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    seo_description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    brief: Mapped[str | None] = mapped_column(Text, nullable=True)       # SEO-бриф (пока ручной)
    draft_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Блоки редактора из 11.7 (Этап 2)
    faq: Mapped[str | None] = mapped_column(Text, nullable=True)
    cta: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    internal_links: Mapped[str | None] = mapped_column(Text, nullable=True)   # ссылки на курсы EFFEСOM
    sources_list: Mapped[str | None] = mapped_column(Text, nullable=True)     # источники статьи
    effecom_block: Mapped[str | None] = mapped_column(Text, nullable=True)    # «Как EFFEСOM может помочь»
    # Планирование публикации (11.8, Этап 2)
    planned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[ArticleStatus] = mapped_column(Enum(ArticleStatus), default=ArticleStatus.draft)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    topic: Mapped[Topic | None] = relationship()
    responsible: Mapped[User | None] = relationship()
    versions: Mapped[list["ArticleVersion"]] = relationship(
        back_populates="article", cascade="all, delete-orphan")
    checklist: Mapped[list["ArticleChecklistItem"]] = relationship(
        back_populates="article", cascade="all, delete-orphan")
    comments: Mapped[list["ArticleComment"]] = relationship(
        back_populates="article", cascade="all, delete-orphan")


# ------------------------------------------------------------ Инфоповоды (11.5)
class InfoEventStatus(str, enum.Enum):
    new = "new"                      # Новый
    in_progress = "in_progress"      # В работе
    topic_created = "topic_created"  # Создана тема
    rejected = "rejected"            # Отклонён
    archived = "archived"            # Архив


class Importance(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class InfoEvent(Base):
    """Инфоповод — найденное изменение/новость/вопрос, из которого можно
    сделать статью. На Этапе 2 создаётся вручную; на Этапе 3 их будет
    предлагать модуль мониторинга источников."""
    __tablename__ = "info_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(255), nullable=True)
    importance: Mapped[Importance] = mapped_column(Enum(Importance), default=Importance.medium)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)           # краткая выжимка
    links: Mapped[str | None] = mapped_column(Text, nullable=True)             # исходные ссылки
    why_important: Mapped[str | None] = mapped_column(Text, nullable=True)     # почему важно клиентам
    related_services: Mapped[str | None] = mapped_column(Text, nullable=True)  # услуги EFFEСOM по теме
    suggested_titles: Mapped[str | None] = mapped_column(Text, nullable=True)  # предложенные заголовки
    status: Mapped[InfoEventStatus] = mapped_column(
        Enum(InfoEventStatus), default=InfoEventStatus.new)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    source: Mapped[Source | None] = relationship()
    responsible: Mapped[User | None] = relationship()


# ------------------------------------------- Версии статьи по каналам (6.8, 11.7)
class VersionChannel(str, enum.Enum):
    site = "site"            # полная SEO-статья
    dzen = "dzen"            # журнальный стиль
    vk = "vk"                # короткая версия с тезисами
    telegram = "telegram"    # короткий пост, 3-5 тезисов
    markdown = "markdown"    # экспорт Markdown/HTML


class VersionStatus(str, enum.Enum):
    draft = "draft"
    ready = "ready"
    published = "published"


class ArticleVersion(Base):
    __tablename__ = "article_versions"
    __table_args__ = (UniqueConstraint("article_id", "channel", name="uq_article_channel"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    channel: Mapped[VersionChannel] = mapped_column(Enum(VersionChannel))
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[VersionStatus] = mapped_column(Enum(VersionStatus), default=VersionStatus.draft)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    article: Mapped["Article"] = relationship(back_populates="versions")


# ------------------------------------------------- Чек-лист качества (6.9, 11.7)
# Пункты автопроверки из 6.9 ТЗ; на Этапе 2 отмечаются вручную,
# на Этапе 3 их будет заполнять модуль проверки качества.
DEFAULT_CHECKLIST: list[tuple[str, str]] = [
    ("sources", "Указаны источники"),
    ("specific", "Текст конкретный, без «воды»"),
    ("practical", "Есть практическая польза и шаги"),
    ("cta", "Есть CTA"),
    ("internal_links", "Есть внутренние ссылки на курсы EFFEСOM"),
    ("no_promises", "Нет запрещённых обещаний и гарантий"),
    ("claims_sourced", "Нет утверждений без источника"),
    ("no_copy", "Нет копирования больших фрагментов"),
    ("legal_safe", "Нет юридически опасных формулировок"),
    ("matches_services", "Тема совпадает с услугами EFFEСOM"),
]


class ArticleChecklistItem(Base):
    __tablename__ = "article_checklist_items"
    __table_args__ = (UniqueConstraint("article_id", "key", name="uq_article_checklist_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(255))
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    article: Mapped["Article"] = relationship(back_populates="checklist")


# --------------------------------------------- Комментарии к статье (11.7.5)
class ArticleComment(Base):
    __tablename__ = "article_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    author_name: Mapped[str] = mapped_column(String(255))
    author_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    article: Mapped["Article"] = relationship(back_populates="comments")


# --------------------------- Тема ← найденные материалы (раздел 9; Этап 4b)
class TopicSourceItem(Base):
    """Из каких найденных материалов родилась тема (11.4.7, 11.15.1).
    Join-таблица: topics и source_items не изменяются."""
    __tablename__ = "topic_source_items"
    __table_args__ = (UniqueConstraint("topic_id", "source_item_id",
                                       name="uq_topic_source_item"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    source_item_id: Mapped[int] = mapped_column(
        ForeignKey("source_items.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ------------------------------- Найденные материалы (раздел 9, 11.4; Этап 4a)
class SourceItemStatus(str, enum.Enum):
    new = "new"                       # найден, ждёт решения редактора
    reviewed = "reviewed"             # просмотрен (AI-анализ выполнен)
    info_event_created = "info_event_created"
    hidden = "hidden"


class SourceItem(Base):
    """Материал, найденный мониторингом. Полный текст НЕ хранится —
    только заголовок, ссылка и выдержка (правовые требования раздела 2)."""
    __tablename__ = "source_items"
    __table_args__ = (UniqueConstraint("source_id", "url", name="uq_source_item_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(1000))
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True)
    excerpt: Mapped[str | None] = mapped_column(String(1500), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)      # ручной AI-анализ
    importance: Mapped[str | None] = mapped_column(String(20), nullable=True)
    relevance_score: Mapped[int] = mapped_column(Integer, default=0)      # keyword-фильтр
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[SourceItemStatus] = mapped_column(
        Enum(SourceItemStatus), default=SourceItemStatus.new, index=True)
    info_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("info_events.id", ondelete="SET NULL"), nullable=True)

    source: Mapped["Source"] = relationship()


class SourceCheckStatus(str, enum.Enum):
    ok = "ok"
    error = "error"
    blocked = "blocked"               # robots.txt или 401/402/403


class SourceCheck(Base):
    __tablename__ = "source_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    status: Mapped[SourceCheckStatus] = mapped_column(
        Enum(SourceCheckStatus), default=SourceCheckStatus.ok)
    found_new: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(String(50), nullable=True)  # worker/manual


# ------------------------------------------ Промпты (11.12, 12 ТЗ; Этап 3)
class Prompt(Base):
    """Редактируемый шаблон промпта. Текущая версия хранится здесь,
    все прошлые — в PromptVersion; версии не удаляются (11.12.839)."""
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    purpose: Mapped[str | None] = mapped_column(String(500), nullable=True)
    template: Mapped[str] = mapped_column(Text)
    variables: Mapped[str | None] = mapped_column(String(500), nullable=True)  # список {переменных}
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    versions: Mapped[list["PromptVersion"]] = relationship(
        back_populates="prompt", cascade="all, delete-orphan")


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("prompt_id", "version", name="uq_prompt_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    prompt_id: Mapped[int] = mapped_column(
        ForeignKey("prompts.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    template: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    prompt: Mapped["Prompt"] = relationship(back_populates="versions")


# ------------------------------- Журнал AI-запросов и расходов (14.11; Этап 3)
class AIRequestStatus(str, enum.Enum):
    ok = "ok"
    error = "error"
    budget_denied = "budget_denied"


class AIRequest(Base):
    __tablename__ = "ai_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(100))              # brief/draft/version_vk/...
    prompt_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    article_id: Mapped[int | None] = mapped_column(
        ForeignKey("articles.id", ondelete="SET NULL"), nullable=True)
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[AIRequestStatus] = mapped_column(
        Enum(AIRequestStatus), default=AIRequestStatus.ok)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True)


# --------------------------------------------------- Журнал действий (14.2.7, 15.4)
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(100))    # login / login_failed / create / update / delete / status_change
    entity: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
