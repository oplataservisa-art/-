#!/usr/bin/env python3
"""Самотест ядра парсинга (Этап 4a) на локальных фикстурах — без сети и БД.

Запуск: python3 scripts/parse_selftest.py  (или в контейнере:
docker compose exec backend python scripts/parse_selftest.py — файл копируется
в образ вместе с backend? нет — запускать с хоста из папки проекта:
PYTHONPATH=backend python3 scripts/parse_selftest.py)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.parsing import (content_hash, parse_html_list, parse_rss,  # noqa: E402
                         parse_source, relevance_score)

FIX = Path(__file__).resolve().parent / "fixtures"
failed = []


def check(name: str, condition: bool, detail: str = ""):
    print(f"  [{'OK' if condition else 'FAIL'}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failed.append(name)


print("Самотест парсера Этапа 4a")

# ---------------------------------------------------------------- RSS 2.0
rss = parse_rss(FIX.joinpath("sample_rss.xml").read_text(encoding="utf-8"),
                "https://example.gov.ru/news")
check("RSS: найдено 4 элемента", len(rss) == 4, f"получено {len(rss)}")
check("RSS: заголовок без HTML-тегов", "<p>" not in rss[0].excerpt and "меняются программы" in rss[0].excerpt)
check("RSS: дата разобрана с таймзоной", rss[0].published_at is not None and rss[0].published_at.tzinfo is not None)
check("RSS: релевантный материал набирает балл", rss[0].relevance_score >= 3)
check("RSS: нерелевантный (цветники) — 0 баллов", rss[2].relevance_score == 0)
check("RSS: дубль (тот же текст, другой URL) даёт тот же content_hash",
      rss[0].content_hash == rss[3].content_hash and rss[0].url != rss[3].url)
check("hash: нормализация регистра и пунктуации",
      content_hash("Охрана труда — 2026!", "Текст.") == content_hash("охрана ТРУДА 2026", "текст"))

# ------------------------------------------------------------------- Atom
atom = parse_rss(FIX.joinpath("sample_atom.xml").read_text(encoding="utf-8"),
                 "https://example.legal.ru")
check("Atom: найден 1 entry", len(atom) == 1, f"получено {len(atom)}")
check("Atom: ссылка и релевантность (ОПО)", atom and atom[0].url.endswith("/atom/21") and atom[0].relevance_score > 0)

# ------------------------------------------------------------- HTML-список
html_items = parse_html_list(FIX.joinpath("sample_list.html").read_text(encoding="utf-8"),
                             "https://fixture.example.ru/news/")
urls = [i.url for i in html_items]
check("HTML: найдены 2 новости из списка", len(html_items) == 2, f"получено {len(html_items)}: {urls}")
check("HTML: относительная ссылка достроена до абсолютной",
      any(u == "https://fixture.example.ru/news/2026/obuchenie-po-ohrane-truda-novye-pravila" for u in urls))
check("HTML: чужой домен отфильтрован", not any("other-site" in u for u in urls))
check("HTML: навигация/подписка/короткие ссылки отфильтрованы",
      not any("/login" in u or "/promo/" in u or "/contacts" in u for u in urls))
check("HTML: секция сайта соблюдена (только /news)", all("/news/" in u for u in urls))

# --------------------------------------------------------- автоопределение
auto = parse_source(FIX.joinpath("sample_rss.xml").read_text(encoding="utf-8"),
                    "https://example.gov.ru/rss")
check("parse_source: XML распознан как лента", len(auto) == 4)
auto2 = parse_source(FIX.joinpath("sample_list.html").read_text(encoding="utf-8"),
                     "https://fixture.example.ru/news/")
check("parse_source: HTML распознан как список", len(auto2) == 2)

# ------------------------------------------------------------ релевантность
check("relevance: заголовок весит больше выдержки",
      relevance_score("Обучение по охране труда", "") > relevance_score("Новость", "обучение по охране труда"))

print()
if failed:
    print(f"ПРОВАЛЕНО: {len(failed)} — {failed}")
    sys.exit(1)
print("Все проверки парсера пройдены.")
