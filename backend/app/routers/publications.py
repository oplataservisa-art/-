"""Публикации: экспорт, предпросмотр, ручная фиксация и лог (Этап 4).

Строго по ТЗ 4/6.8/6.10/11.7:
- экспорт версии/статьи в Markdown и HTML (ручной, §4/§6.8, критерий MVP №9);
- предпросмотр версии перед публикацией (6.10 #1);
- ручное подтверждение факта публикации по каналу со ссылкой (6.10 #2,#4,#5);
- лог публикаций (6.10 #3).

Экспорт и рендер — чистые шаблоны/строки, БЕЗ AI и БЕЗ внешних вызовов.
Автопубликации нет: строку Publication создаёт только контент-менеджер
явным подтверждением (POST /publish).
"""
from datetime import datetime, timezone
from html import escape
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import (Article, ArticleStatus, ArticleVersion, Publication,
                      PublicationStatus, Role, User, VersionChannel)
from ..schemas import PublicationOut, PublishIn
from ..security import (allowed_transitions_for, client_ip, get_current_user,
                        require_roles)

router = APIRouter(prefix="/api/articles", tags=["publications"])

can_export = require_roles(Role.editor, Role.content_manager)
can_publish = require_roles(Role.content_manager)

# Ручная фиксация допускается только когда статья реально дошла до публикации.
# Статусы ready/scheduled/published достижимы лишь через редакционный гейт
# (переход в «Готова» требует полного чек-листа), поэтому проверка статуса
# заодно защищает и чек-лист — обойти его через /publish нельзя.
PUBLISHABLE_STATUSES = {
    ArticleStatus.ready, ArticleStatus.scheduled, ArticleStatus.published,
}
# Каналы, для которых при успешной публикации обязательна ссылка на материал.
# markdown — это файловый экспорт, публичной ссылки у него нет.
URL_REQUIRED_CHANNELS = {
    VersionChannel.site, VersionChannel.dzen,
    VersionChannel.vk, VersionChannel.telegram,
}


def _get_article(db: Session, article_id: int) -> Article:
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(404, "Статья не найдена")
    return article


def _slug(article: Article) -> str:
    """ASCII-слаг для имени файла. HTTP-заголовки кодируются latin-1, поэтому
    кириллица и прочие не-ASCII символы недопустимы — транслитерируем."""
    base = (article.slug or article.title or f"article-{article.id}").strip().lower()
    translit = str.maketrans(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
        "abvgdeejziyklmnoprstufhccss-y-eua")
    base = base.translate(translit)
    safe = "".join(c if (c.isascii() and (c.isalnum() or c in "-_")) else "-"
                   for c in base)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or f"article-{article.id}"


def _markdown(article: Article, version: ArticleVersion | None) -> str:
    """Собрать Markdown из версии канала или, если её нет, из полей статьи."""
    if version is not None:
        title = version.title or article.title
        parts = [f"# {title}", "", (version.body or "").strip()]
        return "\n".join(parts).strip() + "\n"

    parts = [f"# {article.title}", ""]
    body = (article.final_text or article.draft_text or "").strip()
    if body:
        parts += [body, ""]
    if article.faq:
        parts += ["## FAQ", "", article.faq.strip(), ""]
    if article.effecom_block:
        parts += ["## Как EFFEСOM может помочь", "", article.effecom_block.strip(), ""]
    if article.cta:
        parts += [f"**CTA:** {article.cta.strip()}", ""]
    if article.internal_links:
        parts += ["## Полезные ссылки", "", article.internal_links.strip(), ""]
    if article.sources_list:
        parts += ["## Источники", "", article.sources_list.strip(), ""]
    return "\n".join(parts).strip() + "\n"


def _md_to_html(md: str) -> str:
    """Минимальный безопасный рендер Markdown→HTML без внешних зависимостей.

    Поддержаны заголовки #/##/###, абзацы и **жирный**. Весь текст экранируется,
    поэтому вставка HTML из контента невозможна (защита от инъекций)."""
    html_lines: list[str] = []
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("### "):
            html_lines.append(f"<h3>{_inline(line[4:])}</h3>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("# "):
            html_lines.append(f"<h1>{_inline(line[2:])}</h1>")
        else:
            html_lines.append(f"<p>{_inline(line)}</p>")
    return "\n".join(html_lines)


def _inline(text: str) -> str:
    safe = escape(text)
    # **жирный** → <strong> (после экранирования, работаем с безопасным текстом)
    out, bold = [], False
    i = 0
    while i < len(safe):
        if safe[i:i + 2] == "**":
            out.append("</strong>" if bold else "<strong>")
            bold = not bold
            i += 2
        else:
            out.append(safe[i])
            i += 1
    if bold:
        out.append("</strong>")
    return "".join(out)


def _html_document(title: str, md: str) -> str:
    return (
        "<!DOCTYPE html>\n<html lang=\"ru\"><head><meta charset=\"utf-8\">"
        f"<title>{escape(title)}</title></head>\n<body>\n"
        f"{_md_to_html(md)}\n</body></html>\n"
    )


def _version_for(db: Session, article_id: int,
                 channel: VersionChannel | None) -> ArticleVersion | None:
    if channel is None:
        return None
    return db.scalar(select(ArticleVersion).where(
        ArticleVersion.article_id == article_id,
        ArticleVersion.channel == channel))


@router.get("/{article_id}/export")
def export_article(article_id: int,
                   format: Literal["md", "html"] = "md",
                   channel: VersionChannel | None = None,
                   db: Session = Depends(get_db),
                   user: User = Depends(can_export)):
    """Экспорт в Markdown или HTML (ручной, §4/§6.8). DOCX в этот этап не входит."""
    article = _get_article(db, article_id)
    version = _version_for(db, article_id, channel)
    md = _markdown(article, version)
    slug = _slug(article)
    if format == "html":
        content = _html_document(version.title if version else article.title, md)
        media, ext = "text/html; charset=utf-8", "html"
    else:
        content, media, ext = md, "text/markdown; charset=utf-8", "md"
    suffix = f"-{channel.value}" if channel else ""
    filename = f"{slug}{suffix}.{ext}"
    return Response(content=content, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{article_id}/preview")
def preview_version(article_id: int, channel: VersionChannel | None = None,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Предпросмотр публикации (6.10 #1): отрендеренный HTML версии/статьи."""
    article = _get_article(db, article_id)
    version = _version_for(db, article_id, channel)
    md = _markdown(article, version)
    return {"channel": channel.value if channel else "site",
            "title": (version.title if version else article.title),
            "html": _md_to_html(md)}


@router.get("/{article_id}/publications", response_model=list[PublicationOut])
def list_publications(article_id: int, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """Лог публикаций статьи (6.10 #3)."""
    _get_article(db, article_id)
    return db.scalars(select(Publication).where(
        Publication.article_id == article_id)
        .order_by(Publication.id.desc())).all()


@router.post("/{article_id}/publish", response_model=PublicationOut, status_code=201)
def publish_channel(article_id: int, data: PublishIn, request: Request,
                    db: Session = Depends(get_db),
                    user: User = Depends(can_publish)):
    """Ручная фиксация факта публикации по каналу со ссылкой (6.10 #2,#4,#5).

    НЕ обращается к внешним API и НЕ публикует автоматически — только записывает
    подтверждённый пользователем факт и обновляет статусы. Автопубликация
    отсутствует (критерий MVP №10)."""
    article = _get_article(db, article_id)

    # Редакционный гейт: нельзя фиксировать публикацию, пока статья не доведена
    # до публикуемого статуса (чек-лист качества обязателен для перехода в «Готова»).
    if article.status not in PUBLISHABLE_STATUSES:
        raise HTTPException(
            409,
            f"Статью в статусе «{article.status.value}» публиковать нельзя. "
            "Сначала доведите её до «Готова к публикации» — это требует "
            "полностью закрытого чек-листа качества.")

    # Обязательность ссылки/описания ошибки (без внешних вызовов).
    if data.status == PublicationStatus.published:
        if data.channel in URL_REQUIRED_CHANNELS and not (data.publication_url or "").strip():
            raise HTTPException(
                422,
                f"Для канала «{data.channel.value}» при статусе «опубликовано» "
                "нужна ссылка на опубликованный материал.")
    elif data.status == PublicationStatus.error:
        if not (data.error_log or "").strip():
            raise HTTPException(
                422,
                "Для статуса «ошибка публикации» укажите описание ошибки.")

    version = _version_for(db, article_id, data.channel)

    pub = Publication(
        article_id=article.id,
        article_version_id=version.id if version else None,
        channel=data.channel,
        publication_url=data.publication_url,
        status=data.status,
        error_log=data.error_log,
        published_at=data.published_at or (
            datetime.now(timezone.utc) if data.status == PublicationStatus.published else None),
    )
    db.add(pub)

    # Обновляем статусы аккуратно, не ломая принятую машину состояний.
    if data.status == PublicationStatus.published:
        if version is not None and version.published_at is None:
            version.published_at = pub.published_at
        if ArticleStatus.published in allowed_transitions_for(user, article.status):
            article.status = ArticleStatus.published
            if article.published_at is None:
                article.published_at = pub.published_at
    elif data.status == PublicationStatus.error:
        if ArticleStatus.publish_error in allowed_transitions_for(user, article.status):
            article.status = ArticleStatus.publish_error

    db.commit()
    db.refresh(pub)
    log_action(db, user=user, action="publish", entity="publication", entity_id=pub.id,
               detail=(f"«{article.title}» → {data.channel.value}: "
                       f"{data.status.value}" + (f", {data.publication_url}"
                                                 if data.publication_url else "")),
               ip=client_ip(request))
    return pub
