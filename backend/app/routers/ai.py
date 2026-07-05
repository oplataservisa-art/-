"""AI-действия Этапа 3 (разделы 6.6-6.9, 11.7, 11.15, 14.11 ТЗ).

Принципы:
- все результаты сохраняются только как черновики; публикаций нет;
- существующий текст не перезаписывается без подтверждения (overwrite=true);
- в промпты уходит только контент (тема, бриф, текст, база знаний) —
  никаких настроек, ключей и паролей;
- каждый запрос журналируется в ai_requests с токенами и стоимостью;
  дневной и месячный бюджет проверяются ДО запроса (14.11.7);
- повторный запуск той же операции блокируется, пока не завершится первый;
- при любой ошибке AI данные пользователя не изменяются (11.15.9).
"""
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai import AIError, AIResult, ai_configured, extract_json, generate
from ..audit import log_action
from ..config import settings
from ..database import get_db
from ..models import (AIRequest, AIRequestStatus, Article, ArticleComment,
                      ArticleStatus, ArticleVersion, KnowledgeBaseItem,
                      KnowledgeType, Prompt, Role, Topic, TopicStatus, User,
                      VersionChannel)
from ..prompts_seed import SYSTEM_PROMPT
from ..routers.articles import ensure_checklist, get_or_404
from ..schemas import AIActionIn, ArticleOut, CommentOut
from ..security import client_ip, get_current_user, require_roles

router = APIRouter(prefix="/api/ai", tags=["ai"])

can_generate = require_roles(Role.editor)          # генерация: редактор и админ

# Статусы, в которых допустима генерация в черновик (совпадает с правами
# редактирования Этапа 2; проверки и автопроверка качества дополнительно
# разрешены на экспертной проверке)
EDITABLE = {ArticleStatus.draft, ArticleStatus.needs_revision, ArticleStatus.editing}
CHECKABLE = EDITABLE | {ArticleStatus.expert_review}


def _require_ai() -> None:
    """AI-off режим: без настроенного провайдера все AI-действия отвечают
    503 с понятным текстом ещё до любых других проверок."""
    if not ai_configured():
        raise HTTPException(503, "AI не настроен: задайте AI_PROVIDER, AI_API_KEY "
                                 "и AI_MODEL в .env и перезапустите backend")


# ------------------------------------------------- защита от двойного запуска
_active: set[str] = set()
_active_guard = threading.Lock()


@contextmanager
def one_at_a_time(key: str):
    with _active_guard:
        if key in _active:
            raise HTTPException(409, "Эта AI-операция уже выполняется — дождитесь завершения")
        _active.add(key)
    try:
        yield
    finally:
        with _active_guard:
            _active.discard(key)


# ------------------------------------------------------------------- бюджет
def _spent_since(db: Session, since: datetime) -> float:
    return float(db.scalar(
        select(func.coalesce(func.sum(AIRequest.cost_usd), 0.0))
        .where(AIRequest.created_at >= since,
               AIRequest.status == AIRequestStatus.ok)) or 0.0)


def spending(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return {"today": round(_spent_since(db, day), 4),
            "month": round(_spent_since(db, month), 4)}


def _check_budget(db: Session, user: User, kind: str,
                  article_id: int | None, topic_id: int | None) -> None:
    spent = spending(db)
    over_day = settings.ai_daily_budget_usd > 0 and spent["today"] >= settings.ai_daily_budget_usd
    over_month = settings.ai_monthly_budget_usd > 0 and spent["month"] >= settings.ai_monthly_budget_usd
    if over_day or over_month:
        db.add(AIRequest(kind=kind, article_id=article_id, topic_id=topic_id,
                         status=AIRequestStatus.budget_denied,
                         error="Достигнут лимит бюджета",
                         created_by_email=user.email))
        db.commit()
        limit = "дневной" if over_day else "месячный"
        raise HTTPException(
            409, f"Достигнут {limit} лимит бюджета AI — запросы приостановлены. "
                 "Лимиты задаются в .env (AI_DAILY_BUDGET_USD / AI_MONTHLY_BUDGET_USD).")


# --------------------------------------------------------- запуск промпта
class _SafeDict(dict):
    def __missing__(self, key):  # отсутствующая переменная -> пустая строка
        return ""


def run_prompt(db: Session, user: User, key: str, variables: dict,
               kind: str, article_id: int | None = None,
               topic_id: int | None = None) -> str:
    if not ai_configured():
        raise HTTPException(503, "AI не настроен: задайте AI_PROVIDER, AI_API_KEY "
                                 "и AI_MODEL в .env и перезапустите backend")
    _check_budget(db, user, kind, article_id, topic_id)

    prompt = db.scalar(select(Prompt).where(Prompt.key == key))
    if prompt is None:
        raise HTTPException(500, f"Промпт «{key}» не найден — проверьте экран «Промпты»")

    rendered = prompt.template.format_map(_SafeDict(variables))
    record = AIRequest(kind=kind, prompt_key=key, prompt_version=prompt.version,
                       article_id=article_id, topic_id=topic_id,
                       created_by_email=user.email)
    try:
        result: AIResult = generate(SYSTEM_PROMPT, rendered)
    except AIError as exc:
        record.status = AIRequestStatus.error
        record.error = str(exc)
        db.add(record)
        db.commit()
        raise HTTPException(502, str(exc))

    record.provider = result.provider
    record.model = result.model
    record.input_tokens = result.input_tokens
    record.output_tokens = result.output_tokens
    record.cost_usd = result.cost_usd
    db.add(record)
    db.commit()
    return result.text.strip()


# --------------------------------------------------- контекст базы знаний (6.4)
KB_ORDER = [KnowledgeType.forbidden_phrases, KnowledgeType.legal_limits,
            KnowledgeType.brand_style, KnowledgeType.advantages,
            KnowledgeType.course, KnowledgeType.direction,
            KnowledgeType.pricing, KnowledgeType.faq]
KB_TOTAL_LIMIT = 6000
KB_ITEM_LIMIT = 400


def knowledge_context(db: Session, types: list[KnowledgeType] | None = None) -> str:
    """Актуальные записи базы знаний одним текстом. Только контент —
    без настроек и секретов (14.11.1)."""
    wanted = types or KB_ORDER
    rows = db.scalars(select(KnowledgeBaseItem)
                      .where(KnowledgeBaseItem.is_actual == True,  # noqa: E712
                             KnowledgeBaseItem.type.in_(wanted))).all()
    by_type: dict[KnowledgeType, list[KnowledgeBaseItem]] = {}
    for row in rows:
        by_type.setdefault(row.type, []).append(row)
    parts, total = [], 0
    for kb_type in wanted:
        for item in by_type.get(kb_type, []):
            content = (item.content or "").strip()[:KB_ITEM_LIMIT]
            line = f"[{kb_type.value}] {item.title}: {content}"
            if total + len(line) > KB_TOTAL_LIMIT:
                return "\n".join(parts)
            parts.append(line)
            total += len(line)
    return "\n".join(parts) or "(база знаний пока пуста)"


def services_context(db: Session) -> str:
    rows = db.scalars(select(KnowledgeBaseItem)
                      .where(KnowledgeBaseItem.is_actual == True,  # noqa: E712
                             KnowledgeBaseItem.type.in_(
                                 [KnowledgeType.course, KnowledgeType.direction]))).all()
    return "; ".join(r.title for r in rows) or "(курсы не заведены в базе знаний)"


# ------------------------------------------------------------------- статус
@router.get("/status")
def ai_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    out = {"configured": ai_configured(),
           "provider": settings.ai_provider or None,
           "model": settings.ai_model or None}
    if user.role == Role.admin:
        out["spending"] = spending(db)
        out["budgets"] = {"daily_usd": settings.ai_daily_budget_usd,
                          "monthly_usd": settings.ai_monthly_budget_usd}
    return out


# ------------------------------------------------- бриф из темы (11.15.2)
@router.post("/topics/{topic_id}/brief", response_model=ArticleOut, status_code=201)
def brief_from_topic(topic_id: int, request: Request,
                     db: Session = Depends(get_db),
                     user: User = Depends(can_generate)):
    _require_ai()
    """Создать SEO-бриф из темы за 1 клик: создаётся черновик статьи
    с заполненным брифом, тема переходит в «Бриф готов»."""
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(404, "Тема не найдена")
    if topic.status in (TopicStatus.rejected, TopicStatus.archived):
        raise HTTPException(409, "Тема отклонена или в архиве — верните её в работу")

    with one_at_a_time(f"topic_brief:{topic_id}"):
        brief = run_prompt(db, user, "seo_brief", {
            "topic_title": topic.title, "direction": topic.direction or "",
            "audience": topic.audience or "", "intent": topic.intent or "",
            "keywords": topic.keywords or "", "channel": topic.channel or "site",
            "cta": topic.cta or "", "knowledge": knowledge_context(db),
        }, kind="brief", topic_id=topic_id)

        article = Article(title=topic.title, topic_id=topic.id,
                          channel=topic.channel or "site", brief=brief,
                          responsible_id=user.id)
        db.add(article)
        topic.status = TopicStatus.brief_ready
        db.commit()
        db.refresh(article)
        log_action(db, user=user, action="ai_generate", entity="article",
                   entity_id=article.id,
                   detail=f"AI создал SEO-бриф и черновик по теме «{topic.title}»",
                   ip=client_ip(request))
        from ..routers.articles import to_out
        return to_out(article, user)


# ----------------------------------------------- бриф в существующей статье
@router.post("/articles/{article_id}/brief", response_model=ArticleOut)
def brief_for_article(article_id: int, data: AIActionIn, request: Request,
                      db: Session = Depends(get_db),
                      user: User = Depends(can_generate)):
    _require_ai()
    article = get_or_404(db, article_id)
    _ensure_editable(article, user)
    if (article.brief or "").strip() and not data.overwrite:
        raise HTTPException(409, "У статьи уже есть бриф. Подтвердите перезапись — "
                                 "текущий бриф будет заменён.")
    topic = article.topic
    with one_at_a_time(f"brief:{article_id}"):
        brief = run_prompt(db, user, "seo_brief", {
            "topic_title": article.title,
            "direction": (topic.direction if topic else "") or "",
            "audience": (topic.audience if topic else "") or "",
            "intent": (topic.intent if topic else "") or "",
            "keywords": (topic.keywords if topic else "") or "",
            "channel": article.channel or "site",
            "cta": (topic.cta if topic else "") or "",
            "knowledge": knowledge_context(db),
        }, kind="brief", article_id=article_id)
        article.brief = brief
        if topic and topic.status in (TopicStatus.idea, TopicStatus.needs_brief):
            topic.status = TopicStatus.brief_ready
        db.commit()
        db.refresh(article)
        log_action(db, user=user, action="ai_generate", entity="article",
                   entity_id=article.id, detail="AI сгенерировал SEO-бриф",
                   ip=client_ip(request))
        from ..routers.articles import to_out
        return to_out(article, user)


# --------------------------------------- черновик статьи по брифу (11.15.3)
@router.post("/articles/{article_id}/draft", response_model=ArticleOut)
def draft_for_article(article_id: int, data: AIActionIn, request: Request,
                      db: Session = Depends(get_db),
                      user: User = Depends(can_generate)):
    _require_ai()
    article = get_or_404(db, article_id)
    _ensure_editable(article, user)
    if not (article.brief or "").strip():
        raise HTTPException(409, "Сначала создайте SEO-бриф — статья пишется по брифу (6.7)")
    if (article.draft_text or "").strip() and not data.overwrite:
        raise HTTPException(409, "Черновик уже есть. Подтвердите перезапись — "
                                 "текущий черновик будет заменён (финальный текст не трогается).")

    with one_at_a_time(f"draft:{article_id}"):
        raw = run_prompt(db, user, "article_site", {
            "topic_title": article.title,
            "brief": article.brief,
            "knowledge": knowledge_context(db),
            "sources": article.sources_list or "",
        }, kind="draft", article_id=article_id)
        payload = extract_json(raw)

        article.draft_text = str(payload.get("draft_text") or "").strip() or article.draft_text
        # Вспомогательные поля заполняем только если они пустые —
        # существующее содержимое без подтверждения не трогаем (правило 9)
        for field in ("seo_title", "seo_description", "slug", "faq", "cta",
                      "internal_links", "sources_list", "effecom_block"):
            new_value = str(payload.get(field) or "").strip()
            if new_value and not (getattr(article, field) or "").strip():
                setattr(article, field, new_value)
        db.commit()
        db.refresh(article)
        log_action(db, user=user, action="ai_generate", entity="article",
                   entity_id=article.id, detail="AI сгенерировал черновик статьи",
                   ip=client_ip(request))
        from ..routers.articles import to_out
        return to_out(article, user)


# ------------------------------------------- версии по каналам AI (11.15.4)
AI_VERSION_PROMPTS = {VersionChannel.dzen: "adapt_dzen",
                      VersionChannel.vk: "adapt_vk",
                      VersionChannel.telegram: "adapt_telegram"}


@router.post("/articles/{article_id}/versions")
def versions_for_article(article_id: int, data: AIActionIn, request: Request,
                         db: Session = Depends(get_db),
                         user: User = Depends(can_generate)):
    """AI-версии для Дзена, VK и Telegram (6.8). Версия «Сайт» — это сама
    статья, «HTML/Markdown» — экспортная копия; их AI не пересочиняет.
    Существующие непустые версии без overwrite пропускаются."""
    _require_ai()
    article = get_or_404(db, article_id)
    base_text = (article.final_text or article.draft_text or "").strip()
    if not base_text:
        raise HTTPException(409, "Сначала нужен текст статьи (черновик или финальный)")

    with one_at_a_time(f"versions:{article_id}"):
        made, skipped = [], []
        for channel, prompt_key in AI_VERSION_PROMPTS.items():
            version = db.scalar(select(ArticleVersion).where(
                ArticleVersion.article_id == article_id,
                ArticleVersion.channel == channel))
            if version is not None and (version.body or "").strip() and not data.overwrite:
                skipped.append(channel.value)
                continue
            text = run_prompt(db, user, prompt_key,
                              {"title": article.title, "article": base_text},
                              kind=f"version_{channel.value}", article_id=article_id)
            if version is None:
                version = ArticleVersion(article_id=article.id, channel=channel)
                db.add(version)
            version.title = version.title or article.title
            version.body = text                      # статус версии остаётся draft
            db.commit()
            made.append(channel.value)
        if made:
            log_action(db, user=user, action="ai_generate", entity="article_version",
                       entity_id=article.id,
                       detail=f"AI создал версии: {', '.join(made)}",
                       ip=client_ip(request))
        return {"generated": made, "skipped": skipped,
                "detail": ("Пропущены непустые версии: " + ", ".join(skipped) +
                           " — запустите с подтверждением перезаписи, чтобы обновить их")
                          if skipped else "Готово"}


# --------------------------------------------------------- улучшить текст
@router.post("/articles/{article_id}/improve", response_model=ArticleOut)
def improve_article(article_id: int, data: AIActionIn, request: Request,
                    db: Session = Depends(get_db),
                    user: User = Depends(can_generate)):
    _require_ai()
    article = get_or_404(db, article_id)
    _ensure_editable(article, user)
    if not (article.draft_text or "").strip():
        raise HTTPException(409, "Черновик пуст — улучшать нечего")
    if not data.overwrite:
        raise HTTPException(409, "Улучшение заменит текущий черновик. Подтвердите "
                                 "перезапись (финальный текст не трогается).")
    with one_at_a_time(f"improve:{article_id}"):
        text = run_prompt(db, user, "improve_text", {
            "title": article.title, "article": article.draft_text,
            "knowledge": knowledge_context(db),
        }, kind="improve", article_id=article_id)
        article.draft_text = text
        db.commit()
        db.refresh(article)
        log_action(db, user=user, action="ai_generate", entity="article",
                   entity_id=article.id, detail="AI улучшил черновик",
                   ip=client_ip(request))
        from ..routers.articles import to_out
        return to_out(article, user)


# ------------------------------------- проверки: факты и юридические риски
def _run_check(article_id: int, request: Request, db: Session, user: User,
               prompt_key: str, kind: str, extra: dict, label: str) -> ArticleComment:
    _require_ai()
    article = get_or_404(db, article_id)
    if article.status not in CHECKABLE and user.role != Role.admin:
        raise HTTPException(409, f"Проверка доступна до публикации; сейчас статус "
                                 f"«{article.status.value}»")
    text_source = (article.final_text or article.draft_text or "").strip()
    if not text_source:
        raise HTTPException(409, "Текста для проверки нет")
    with one_at_a_time(f"{kind}:{article_id}"):
        report = run_prompt(db, user, prompt_key,
                            {"title": article.title, "article": text_source, **extra},
                            kind=kind, article_id=article_id)
        comment = ArticleComment(article_id=article.id, author_id=None,
                                 author_name=label, author_role="ai",
                                 text=report)
        db.add(comment)
        db.commit()
        db.refresh(comment)
        log_action(db, user=user, action="ai_check", entity="article",
                   entity_id=article.id, detail=label, ip=client_ip(request))
        return comment


@router.post("/articles/{article_id}/check-facts", response_model=CommentOut, status_code=201)
def check_facts(article_id: int, request: Request, db: Session = Depends(get_db),
                user: User = Depends(can_generate)):
    return _run_check(article_id, request, db, user, "check_facts", "check_facts",
                      {"sources": ""}, "AI-проверка фактов")


@router.post("/articles/{article_id}/check-legal", response_model=CommentOut, status_code=201)
def check_legal(article_id: int, request: Request, db: Session = Depends(get_db),
                user: User = Depends(can_generate)):
    return _run_check(article_id, request, db, user, "check_legal", "check_legal",
                      {"legal_limits": knowledge_context(
                          db, [KnowledgeType.legal_limits, KnowledgeType.forbidden_phrases])},
                      "AI-проверка юридических рисков")


# --------------------------------------- автопроверка качества (6.9)
@router.post("/articles/{article_id}/quality")
def quality_check(article_id: int, request: Request,
                  db: Session = Depends(get_db),
                  user: User = Depends(can_generate)):
    """AI только ПРЕДЛАГАЕТ отметки чек-листа (updated_by='AI'): человек
    (редактор/эксперт) может снять или изменить любую; гейт перехода
    в «Готова к публикации» из Этапа 2 не меняется."""
    _require_ai()
    article = get_or_404(db, article_id)
    if article.status not in CHECKABLE and user.role != Role.admin:
        raise HTTPException(409, "Автопроверка доступна до публикации")
    text_source = (article.final_text or article.draft_text or "").strip()
    if not text_source:
        raise HTTPException(409, "Текста для проверки нет")

    with one_at_a_time(f"quality:{article_id}"):
        raw = run_prompt(db, user, "quality_check", {
            "title": article.title, "article": text_source,
            "faq": article.faq or "", "cta": article.cta or "",
            "internal_links": article.internal_links or "",
            "sources": article.sources_list or "",
            "effecom_block": article.effecom_block or "",
            "services": services_context(db),
        }, kind="quality", article_id=article_id)
        verdicts = extract_json(raw)

        items = ensure_checklist(db, article)
        applied = 0
        for item in items:
            verdict = verdicts.get(item.key)
            if not isinstance(verdict, dict):
                continue
            item.is_done = bool(verdict.get("done"))
            item.comment = str(verdict.get("comment") or "")[:1000] or None
            item.updated_by = "AI"
            applied += 1
        db.commit()
        log_action(db, user=user, action="ai_check", entity="article",
                   entity_id=article.id,
                   detail=f"AI-автопроверка качества: оценено пунктов — {applied}",
                   ip=client_ip(request))
        done = sum(1 for i in items if i.is_done)
        return {"applied": applied, "done": done, "total": len(items),
                "detail": "Отметки предложены AI — эксперт может изменить любую"}


def _ensure_editable(article: Article, user: User) -> None:
    if article.status not in EDITABLE and user.role != Role.admin:
        raise HTTPException(409, f"Статья в статусе «{article.status.value}» — "
                                 "генерация в черновик доступна только на этапах "
                                 "редактирования; верните статью на доработку")
