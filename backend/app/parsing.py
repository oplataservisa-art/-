"""Ядро мониторинга источников (Этап 4a, разделы 6.1-6.2 ТЗ).

Чистые функции без обращения к базе — их проверяет scripts/parse_selftest.py
на локальных фикстурах без сети.

Правовые и технические гарантии (раздел 2 ТЗ и требования этапа):
- robots.txt уважается: запрет → источник не загружается вообще;
- запросы анонимные (без кук и авторизации), честный User-Agent,
  обязательный таймаут, лимит размера ответа, максимум 3 редиректа;
- 401/402/403 трактуются как «закрытый/платный раздел» — не парсим;
- полный текст материалов НЕ сохраняется: только заголовок, ссылка,
  дата и выдержка до EXCERPT_LIMIT символов;
- HTML-разбор простой: только список ссылок на странице новостей,
  без обхода сайта. Сложные динамические страницы — допустимое
  ограничение Этапа 4a (см. README).

AI здесь не используется: релевантность первого уровня — обычный
словарь ключевых слов по направлениям EFFEСOM.
"""
import hashlib
import html
import re
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import requests

EXCERPT_LIMIT = 1500
MAX_REDIRECTS = 3

# Ключевые слова направлений EFFEСOM (6.2.3) — правило, не смысловой анализ.
# Совпадение в заголовке весит больше, чем в выдержке.
RELEVANCE_KEYWORDS = [
    "охран труд", "охране труда", "охраны труда", "от-",
    "пожарн", "противопожарн",
    "промышленн безопасн", "промышленной безопасности", "опо",
    "бдд", "дорожн", "перевозк", "транспортн безопасн",
    "обучен", "инструктаж", "стажировк", "квалификац", "дпо",
    "переподготовк", "повышени квалификаци", "рабочих профессий",
    "сиз", "средств индивидуальной защиты",
    "несчастн случа", "производственн травм", "спецоценк", "соут",
    "гит", "трудов инспекц", "минтруд", "ростехнадзор", "мчс",
    "работодател", "штраф", "проверк",
]


class FetchBlocked(Exception):
    """Источник закрыт: robots.txt или требует оплату/авторизацию."""


class FetchError(Exception):
    """Сетевая или HTTP-ошибка при загрузке источника."""


@dataclass
class ParsedItem:
    title: str
    url: str
    published_at: datetime | None = None
    excerpt: str = ""
    relevance_score: int = 0
    content_hash: str = field(default="")

    def finalize(self) -> "ParsedItem":
        self.title = clean_text(self.title)[:500]
        self.excerpt = clean_text(self.excerpt)[:EXCERPT_LIMIT]
        self.relevance_score = relevance_score(self.title, self.excerpt)
        self.content_hash = content_hash(self.title, self.excerpt)
        return self


# ------------------------------------------------------------------ утилиты
def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)          # страховка от тегов в RSS
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def content_hash(title: str, excerpt: str) -> str:
    base = re.sub(r"\W+", "", (title + excerpt).lower())
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def relevance_score(title: str, excerpt: str = "") -> int:
    title_l, excerpt_l = title.lower(), excerpt.lower()
    score = 0
    for kw in RELEVANCE_KEYWORDS:
        if kw in title_l:
            score += 3
        elif kw in excerpt_l:
            score += 1
    return score


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for parser in (parsedate_to_datetime,
                   lambda v: datetime.fromisoformat(v.replace("Z", "+00:00"))):
        try:
            dt = parser(value)
            if dt is not None:
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


# --------------------------------------------------------------- robots.txt
def robots_allows(url: str, fetcher=None) -> bool:
    """True, если robots.txt не запрещает нашему боту этот URL.
    Недоступный robots.txt считается разрешением (стандартная трактовка)."""
    from .config import settings
    parts = urlparse(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    fetcher = fetcher or _fetch_text_quiet
    body = fetcher(robots_url)
    if body is None:
        return True
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(body.splitlines())
    return parser.can_fetch(settings.monitor_user_agent, url)


def _fetch_text_quiet(url: str) -> str | None:
    from .config import settings
    try:
        resp = requests.get(url, timeout=settings.monitor_http_timeout,
                            headers={"User-Agent": settings.monitor_user_agent})
        if resp.status_code == 200:
            return resp.text[: 256 * 1024]
        return None
    except requests.RequestException:
        return None


# ------------------------------------------------------------------ загрузка
def fetch_url(url: str) -> str:
    """Загрузка страницы источника с лимитами. Только открытые страницы."""
    from .config import settings
    try:
        resp = requests.get(
            url,
            timeout=settings.monitor_http_timeout,
            headers={"User-Agent": settings.monitor_user_agent,
                     "Accept": "application/rss+xml, application/atom+xml, "
                               "application/xml, text/html;q=0.9, */*;q=0.5"},
            allow_redirects=True,
            stream=True,
        )
    except requests.Timeout:
        raise FetchError(f"Источник не ответил за {settings.monitor_http_timeout} с")
    except requests.RequestException as exc:
        raise FetchError(f"Сетевая ошибка: {exc.__class__.__name__}")

    if len(resp.history) > MAX_REDIRECTS:
        raise FetchError("Слишком много перенаправлений")
    if resp.status_code in (401, 402, 403):
        raise FetchBlocked("Источник требует авторизацию или оплату — "
                           "закрытые разделы не парсим (раздел 2 ТЗ)")
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}")

    limit = settings.monitor_max_response_kb * 1024
    chunks, total = [], 0
    for chunk in resp.iter_content(chunk_size=16384, decode_unicode=False):
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            break                       # берём первые N КБ — список новостей в начале
    resp.close()
    body = b"".join(chunks)
    encoding = resp.encoding or "utf-8"
    try:
        return body.decode(encoding, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


# ------------------------------------------------------------------ RSS/Atom
def parse_rss(xml_text: str, base_url: str = "") -> list[ParsedItem]:
    """Основной сценарий Этапа 4a: RSS 2.0 и Atom (stdlib, надёжно)."""
    try:
        root = ElementTree.fromstring(xml_text.strip())
    except ElementTree.ParseError as exc:
        raise FetchError(f"Некорректный XML ленты: {exc}")

    items: list[ParsedItem] = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    for node in root.iter("item"):                       # RSS 2.0
        link = (node.findtext("link") or "").strip()
        if not link:
            continue
        items.append(ParsedItem(
            title=node.findtext("title") or "(без заголовка)",
            url=urljoin(base_url, link),
            published_at=parse_date(node.findtext("pubDate")),
            excerpt=node.findtext("description") or "",
        ).finalize())

    if not items:                                        # Atom
        for node in root.iter("{http://www.w3.org/2005/Atom}entry"):
            link_node = node.find("atom:link[@rel='alternate']", ns)
            if link_node is None:
                link_node = node.find("atom:link", ns)
            href = link_node.get("href", "").strip() if link_node is not None else ""
            if not href:
                continue
            items.append(ParsedItem(
                title=node.findtext("atom:title", default="(без заголовка)", namespaces=ns),
                url=urljoin(base_url, href),
                published_at=parse_date(
                    node.findtext("atom:published", default=None, namespaces=ns)
                    or node.findtext("atom:updated", default=None, namespaces=ns)),
                excerpt=node.findtext("atom:summary", default="", namespaces=ns) or "",
            ).finalize())

    return items


# ------------------------------------------------------------- HTML-списки
STOP_LINK_WORDS = ("вход", "войти", "регистрац", "подписк", "поиск", "карта сайта",
                   "контакты", "о нас", "версия для", "cookie", "политик")


def parse_html_list(html_text: str, base_url: str) -> list[ParsedItem]:
    """Базовый разбор страницы-СПИСКА новостей: собираем ссылки с осмысленным
    текстом с той же секции сайта. Сайт целиком не обходим. Если конкретная
    сложная страница не разобралась — это допустимое ограничение Этапа 4a."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "form"]):
        tag.decompose()

    base_parts = urlparse(base_url)
    base_path_root = "/".join(base_parts.path.split("/")[:2])  # /news и т.п.
    seen: set[str] = set()
    items: list[ParsedItem] = []

    for a in soup.find_all("a", href=True):
        text = clean_text(a.get_text())
        if len(text) < 25:                               # меню и «Подробнее» отсекаются
            continue
        if any(w in text.lower() for w in STOP_LINK_WORDS):
            continue
        url = urljoin(base_url, a["href"].split("#")[0])
        parts = urlparse(url)
        if parts.scheme not in ("http", "https") or parts.netloc != base_parts.netloc:
            continue                                     # только тот же сайт
        if base_path_root and not parts.path.startswith(base_path_root):
            continue                                     # только та же секция
        if url in seen or url.rstrip("/") == base_url.rstrip("/"):
            continue
        seen.add(url)
        items.append(ParsedItem(title=text, url=url).finalize())

    return items


def parse_source(body: str, url: str) -> list[ParsedItem]:
    """RSS/Atom — основной путь; иначе HTML-список."""
    head = body.lstrip()[:300].lower()
    if head.startswith("<?xml") or "<rss" in head or "<feed" in head:
        return parse_rss(body, url)
    return parse_html_list(body, url)
