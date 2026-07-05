"""Статьи и редакционный процесс (11.7 ТЗ, Этапы 1-2).

Этап 1: CRUD и машина статусов.
Этап 2: версии по каналам (6.8), чек-лист качества (6.9), комментарии,
планирование публикации (11.8), история изменений.

Переходы статусов идут через отдельный endpoint и проверяются по машине
состояний и по роли пользователя (security.ARTICLE_TRANSITIONS).
Переход в «Готова к публикации» дополнительно требует полностью
закрытого чек-листа качества — так выполняется 11.15.6
(«увидеть, почему статья не готова к публикации»).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import (DEFAULT_CHECKLIST, Article, ArticleChecklistItem,
                      ArticleComment, ArticleStatus, ArticleVersion, Role,
                      Topic, TopicStatus, User, VersionChannel, VersionStatus)
from ..schemas import (ArticleCreate, ArticleOut, ArticleUpdate,
                       ChecklistItemOut, ChecklistItemUpdate, CommentCreate,
                       CommentOut, MarkPublishedIn, ScheduleIn, StatusChangeIn,
                       VersionOut, VersionUpdate)
from ..security import (allowed_transitions_for, client_ip, get_current_user,
                        require_roles)

router = APIRouter(prefix="/api/articles", tags=["articles"])

can_edit = require_roles(Role.editor)
can_check = require_roles(Role.editor, Role.expert)                 # чек-лист
can_version = require_roles(Role.editor, Role.content_manager)      # версии по каналам
can_schedule = require_roles(Role.editor, Role.content_manager)     # планирование (11.8)
can_publish = require_roles(Role.content_manager)                   # отметка «Опубликована»

# Редактировать текст можно только пока статья в работе
EDITABLE_STATUSES = {
    ArticleStatus.draft, ArticleStatus.needs_revision, ArticleStatus.editing,
}


def to_out(article: Article, user: User) -> ArticleOut:
    out = ArticleOut.model_validate(article)
    out.allowed_transitions = allowed_transitions_for(user, article.status)
    out.checklist_total = len(article.checklist) or len(DEFAULT_CHECKLIST)
    out.checklist_done = sum(1 for i in article.checklist if i.is_done)
    return out


def get_or_404(db: Session, article_id: int) -> Article:
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(404, "Статья не найдена")
    return article


def ensure_checklist(db: Session, article: Article) -> list[ArticleChecklistItem]:
    """Ленивое создание чек-листа из шаблона 6.9 при первом обращении."""
    if not article.checklist:
        for key, label in DEFAULT_CHECKLIST:
            db.add(ArticleChecklistItem(article_id=article.id, key=key, label=label))
        db.commit()
        db.refresh(article)
    return sorted(article.checklist, key=lambda i: i.id)


@router.get("", response_model=list[ArticleOut])
def list_articles(status: ArticleStatus | None = Query(default=None),
                  channel: str | None = Query(default=None, max_length=100),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    query = select(Article).order_by(Article.updated_at.desc())
    if status is not None:
        query = query.where(Article.status == status)
    if channel:
        query = query.where(Article.channel == channel)
    return [to_out(a, user) for a in db.scalars(query).all()]


@router.get("/{article_id}", response_model=ArticleOut)
def get_article(article_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(404, "Статья не найдена")
    return to_out(article, user)


@router.post("", response_model=ArticleOut, status_code=201)
def create_article(data: ArticleCreate, request: Request,
                   db: Session = Depends(get_db), user: User = Depends(can_edit)):
    article = Article(**data.model_dump())
    db.add(article)
    # Связанная тема переходит в «Статья создана»
    if article.topic_id:
        topic = db.get(Topic, article.topic_id)
        if topic is None:
            raise HTTPException(400, "Указанная тема не существует")
        topic.status = TopicStatus.article_created
    db.commit()
    db.refresh(article)
    log_action(db, user=user, action="create", entity="article", entity_id=article.id,
               detail=f"Создан черновик статьи «{article.title}»", ip=client_ip(request))
    return to_out(article, user)


@router.put("/{article_id}", response_model=ArticleOut)
def update_article(article_id: int, data: ArticleUpdate, request: Request,
                   db: Session = Depends(get_db), user: User = Depends(can_edit)):
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(404, "Статья не найдена")
    if article.status not in EDITABLE_STATUSES and user.role != Role.admin:
        raise HTTPException(
            409, f"Статья в статусе «{article.status.value}» недоступна для правок. "
                 "Верните её на доработку.")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(article, field, value)
    db.commit()
    db.refresh(article)
    log_action(db, user=user, action="update", entity="article", entity_id=article.id,
               detail=f"Изменена статья «{article.title}»", ip=client_ip(request))
    return to_out(article, user)


@router.post("/{article_id}/status", response_model=ArticleOut)
def change_status(article_id: int, data: StatusChangeIn, request: Request,
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(404, "Статья не найдена")

    allowed = allowed_transitions_for(user, article.status)
    if data.status not in allowed:
        raise HTTPException(
            403, f"Переход «{article.status.value}» → «{data.status.value}» "
                 "недоступен для вашей роли")

    # 11.15.6: статья не может стать «Готова к публикации», пока чек-лист
    # качества не закрыт. В ошибке перечисляем незакрытые пункты.
    if data.status == ArticleStatus.ready and user.role != Role.admin:
        items = ensure_checklist(db, article)
        unfinished = [i.label for i in items if not i.is_done]
        if unfinished:
            raise HTTPException(
                409, "Чек-лист качества не закрыт: " + "; ".join(unfinished))

    # Планирование делается через /schedule, где обязательна дата
    if data.status == ArticleStatus.scheduled and article.planned_at is None:
        raise HTTPException(
            409, "Укажите дату публикации через действие «Запланировать»")

    old = article.status
    article.status = data.status
    if data.status == ArticleStatus.published and article.published_at is None:
        article.published_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(article)
    log_action(db, user=user, action="status_change", entity="article",
               entity_id=article.id,
               detail=f"«{article.title}»: {old.value} → {article.status.value}",
               ip=client_ip(request))
    return to_out(article, user)




# ============================================================ Этап 2: планирование (11.8)
@router.post("/{article_id}/schedule", response_model=ArticleOut)
def schedule_article(article_id: int, data: ScheduleIn, request: Request,
                     db: Session = Depends(get_db),
                     user: User = Depends(can_schedule)):
    """Запланировать публикацию (быстрое действие календаря 11.8).
    Работает из статусов «Готова» и «Запланирована» (перенос даты)."""
    article = get_or_404(db, article_id)
    if article.status == ArticleStatus.ready:
        if ArticleStatus.scheduled not in allowed_transitions_for(user, article.status):
            raise HTTPException(403, "Планирование недоступно для вашей роли")
        article.status = ArticleStatus.scheduled
    elif article.status != ArticleStatus.scheduled:
        raise HTTPException(
            409, f"Планировать можно статью в статусе «Готова к публикации», "
                 f"сейчас — «{article.status.value}»")
    article.planned_at = data.planned_at
    article.review_deadline = data.review_deadline
    db.commit()
    db.refresh(article)
    log_action(db, user=user, action="schedule", entity="article", entity_id=article.id,
               detail=f"«{article.title}» запланирована на {data.planned_at:%d.%m.%Y %H:%M}",
               ip=client_ip(request))
    return to_out(article, user)


@router.post("/{article_id}/mark-published", response_model=ArticleOut)
def mark_published(article_id: int, data: MarkPublishedIn, request: Request,
                   db: Session = Depends(get_db),
                   user: User = Depends(can_publish)):
    """Отметить опубликованной вручную (11.8.5) — интеграций на Этапе 2 нет."""
    article = get_or_404(db, article_id)
    if ArticleStatus.published not in allowed_transitions_for(user, article.status):
        raise HTTPException(
            409, f"Из статуса «{article.status.value}» отметить публикацию нельзя")
    article.status = ArticleStatus.published
    article.published_at = data.published_at or datetime.now(timezone.utc)
    db.commit()
    db.refresh(article)
    log_action(db, user=user, action="publish", entity="article", entity_id=article.id,
               detail=f"«{article.title}» отмечена опубликованной вручную",
               ip=client_ip(request))
    return to_out(article, user)


# ===================================================== Этап 2: версии по каналам (6.8)
# Заготовки под стиль канала из 6.8 ТЗ; на Этапе 3 их заполнит AI.
CHANNEL_HINTS = {
    VersionChannel.site: "Полная SEO-статья: H1/H2/H3, FAQ, внутренние ссылки, CTA.",
    VersionChannel.dzen: "Журнальный стиль: сильное начало, меньше SEO-механики, больше пользы.",
    VersionChannel.vk: "Короткая версия: тезисы, CTA, ссылка на полную статью.",
    VersionChannel.telegram: "Короткий пост: 3-5 тезисов, призыв написать менеджеру.",
    VersionChannel.markdown: "Экспортная версия в Markdown/HTML для других площадок.",
}


@router.get("/{article_id}/versions", response_model=list[VersionOut])
def list_versions(article_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    get_or_404(db, article_id)
    return db.scalars(
        select(ArticleVersion).where(ArticleVersion.article_id == article_id)
        .order_by(ArticleVersion.id)).all()


@router.post("/{article_id}/versions/init", response_model=list[VersionOut])
def init_versions(article_id: int, request: Request,
                  db: Session = Depends(get_db),
                  user: User = Depends(can_version)):
    """Создать версии для каналов за 1 клик (11.15.4). Существующие версии
    не трогаются; недостающие создаются с текстом статьи как основой."""
    article = get_or_404(db, article_id)
    existing = {v.channel for v in article.versions}
    base_text = article.final_text or article.draft_text or ""
    created = 0
    for channel in VersionChannel:
        if channel in existing:
            continue
        body = f"[{CHANNEL_HINTS[channel]}]\n\n{base_text}".strip()
        db.add(ArticleVersion(article_id=article.id, channel=channel,
                              title=article.title, body=body))
        created += 1
    db.commit()
    db.refresh(article)
    if created:
        log_action(db, user=user, action="create", entity="article_version",
                   entity_id=article.id,
                   detail=f"Созданы версии по каналам для «{article.title}» ({created} шт.)",
                   ip=client_ip(request))
    return sorted(article.versions, key=lambda v: v.id)


@router.put("/{article_id}/versions/{channel}", response_model=VersionOut)
def upsert_version(article_id: int, channel: VersionChannel, data: VersionUpdate,
                   request: Request, db: Session = Depends(get_db),
                   user: User = Depends(can_version)):
    article = get_or_404(db, article_id)
    version = db.scalar(select(ArticleVersion).where(
        ArticleVersion.article_id == article_id,
        ArticleVersion.channel == channel))
    if version is None:
        version = ArticleVersion(article_id=article.id, channel=channel,
                                 title=article.title)
        db.add(version)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(version, field, value)
    if version.status == VersionStatus.published and version.published_at is None:
        version.published_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(version)
    log_action(db, user=user, action="update", entity="article_version",
               entity_id=article.id,
               detail=f"Версия «{channel.value}» статьи «{article.title}» обновлена",
               ip=client_ip(request))
    return version


# ====================================================== Этап 2: чек-лист качества (6.9)
@router.get("/{article_id}/checklist", response_model=list[ChecklistItemOut])
def get_checklist(article_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    article = get_or_404(db, article_id)
    return ensure_checklist(db, article)


@router.put("/{article_id}/checklist/{key}", response_model=ChecklistItemOut)
def update_checklist(article_id: int, key: str, data: ChecklistItemUpdate,
                     request: Request, db: Session = Depends(get_db),
                     user: User = Depends(can_check)):
    article = get_or_404(db, article_id)
    ensure_checklist(db, article)
    item = db.scalar(select(ArticleChecklistItem).where(
        ArticleChecklistItem.article_id == article_id,
        ArticleChecklistItem.key == key))
    if item is None:
        raise HTTPException(404, "Пункт чек-листа не найден")
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(item, field, value)
    item.updated_by = user.name
    db.commit()
    db.refresh(item)
    if "is_done" in changes:
        log_action(db, user=user, action="checklist", entity="article",
                   entity_id=article.id,
                   detail=f"«{article.title}»: пункт «{item.label}» — "
                          f"{'выполнен' if item.is_done else 'снят'}",
                   ip=client_ip(request))
    return item


# ========================================================= Этап 2: комментарии (11.7)
@router.get("/{article_id}/comments", response_model=list[CommentOut])
def list_comments(article_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    get_or_404(db, article_id)
    return db.scalars(
        select(ArticleComment).where(ArticleComment.article_id == article_id)
        .order_by(ArticleComment.id)).all()


@router.post("/{article_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(article_id: int, data: CommentCreate, request: Request,
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    article = get_or_404(db, article_id)
    comment = ArticleComment(article_id=article.id, author_id=user.id,
                             author_name=user.name, author_role=user.role.value,
                             text=data.text)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    log_action(db, user=user, action="comment", entity="article",
               entity_id=article.id,
               detail=f"Комментарий к «{article.title}»", ip=client_ip(request))
    return comment


@router.delete("/{article_id}/comments/{comment_id}", status_code=204)
def delete_comment(article_id: int, comment_id: int, request: Request,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    comment = db.get(ArticleComment, comment_id)
    if comment is None or comment.article_id != article_id:
        raise HTTPException(404, "Комментарий не найден")
    if user.role != Role.admin and comment.author_id != user.id:
        raise HTTPException(403, "Удалять можно только свои комментарии")
    db.delete(comment)
    db.commit()
    log_action(db, user=user, action="delete", entity="article_comment",
               entity_id=comment_id, detail="Удалён комментарий",
               ip=client_ip(request))


# ================================================ Этап 2: история изменений (11.7.5)
@router.get("/{article_id}/history")
def article_history(article_id: int,
                    limit: int = Query(default=50, ge=1, le=200),
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """История изменений и публикаций статьи — из журнала действий."""
    from ..models import AuditLog
    get_or_404(db, article_id)
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.entity.in_(["article", "article_version", "article_comment"]),
               AuditLog.entity_id == article_id)
        .order_by(AuditLog.id.desc()).limit(limit)).all()
    return [{"id": r.id, "user_email": r.user_email, "action": r.action,
             "detail": r.detail, "created_at": r.created_at} for r in rows]


@router.delete("/{article_id}", status_code=204)
def delete_article(article_id: int, request: Request,
                   db: Session = Depends(get_db),
                   user: User = Depends(require_roles())):
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(404, "Статья не найдена")
    title = article.title
    db.delete(article)
    db.commit()
    log_action(db, user=user, action="delete", entity="article", entity_id=article_id,
               detail=f"Удалена статья «{title}»", ip=client_ip(request))
