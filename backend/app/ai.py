"""Абстрактный AI-провайдер (Этап 3, раздел 7 ТЗ «абстрактный AI-provider»).

Поддерживаются два семейства API без жёсткой привязки:
- "openai"    — OpenAI и любой совместимый API (через AI_BASE_URL);
- "anthropic" — Anthropic Messages API.

Правила безопасности (14.11):
- ключ берётся ТОЛЬКО из окружения и никуда не передаётся, кроме заголовка
  запроса к провайдеру; в БД, логи и интерфейс не попадает;
- в промпты уходит только контент (тема, бриф, текст, база знаний) —
  функции этого модуля принимают готовые строки и не имеют доступа
  к настройкам, паролям и токенам;
- таймаут обязателен (AI_TIMEOUT_SECONDS), сетевые ошибки превращаются
  в понятный AIError без потери пользовательских данных.

Используется стандартная библиотека (urllib) — без новых зависимостей.
"""
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import settings

logger = logging.getLogger("effecom.ai")

OPENAI_DEFAULT_URL = "https://api.openai.com"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AIError(Exception):
    """Ошибка AI с текстом, пригодным для показа пользователю."""


@dataclass
class AIResult:
    text: str
    input_tokens: int
    output_tokens: int
    provider: str
    model: str

    @property
    def cost_usd(self) -> float:
        return (self.input_tokens * settings.ai_price_input_per_1m
                + self.output_tokens * settings.ai_price_output_per_1m) / 1_000_000


def ai_configured() -> bool:
    return bool(settings.ai_provider and settings.ai_api_key and settings.ai_model)


def _post_json(url: str, headers: dict, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=settings.ai_timeout_seconds) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            pass
        logger.warning("AI HTTP %s: %s", exc.code, detail)
        if exc.code in (401, 403):
            raise AIError("AI-провайдер отклонил ключ доступа — проверьте AI_API_KEY в .env")
        if exc.code == 429:
            raise AIError("AI-провайдер ограничил частоту запросов — повторите чуть позже")
        raise AIError(f"AI-провайдер вернул ошибку {exc.code}" + (f": {detail[:200]}" if detail else ""))
    except TimeoutError:
        raise AIError(f"AI не ответил за {settings.ai_timeout_seconds} с — попробуйте ещё раз")
    except urllib.error.URLError as exc:
        logger.warning("AI network error: %s", exc.reason)
        raise AIError("Нет соединения с AI-провайдером — проверьте сеть и AI_BASE_URL")


def generate(system: str, user: str, max_tokens: int | None = None) -> AIResult:
    """Один синхронный запрос к настроенному провайдеру."""
    if not ai_configured():
        raise AIError("AI не настроен: задайте AI_PROVIDER, AI_API_KEY и AI_MODEL в .env")

    max_tokens = max_tokens or settings.ai_max_output_tokens
    provider = settings.ai_provider.lower().strip()

    if provider == "anthropic":
        data = _post_json(
            ANTHROPIC_URL,
            headers={"x-api-key": settings.ai_api_key,
                     "anthropic-version": ANTHROPIC_VERSION},
            payload={"model": settings.ai_model,
                     "max_tokens": max_tokens,
                     "system": system,
                     "messages": [{"role": "user", "content": user}]})
        try:
            text = "".join(b.get("text", "") for b in data["content"])
            usage = data.get("usage", {})
            return AIResult(text=text,
                            input_tokens=int(usage.get("input_tokens", 0)),
                            output_tokens=int(usage.get("output_tokens", 0)),
                            provider=provider, model=settings.ai_model)
        except (KeyError, TypeError):
            raise AIError("Неожиданный формат ответа Anthropic API")

    if provider == "openai":
        base = (settings.ai_base_url or OPENAI_DEFAULT_URL).rstrip("/")
        data = _post_json(
            f"{base}/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.ai_api_key}"},
            payload={"model": settings.ai_model,
                     "max_tokens": max_tokens,
                     "messages": [{"role": "system", "content": system},
                                  {"role": "user", "content": user}]})
        try:
            text = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage", {})
            return AIResult(text=text,
                            input_tokens=int(usage.get("prompt_tokens", 0)),
                            output_tokens=int(usage.get("completion_tokens", 0)),
                            provider=provider, model=settings.ai_model)
        except (KeyError, IndexError, TypeError):
            raise AIError("Неожиданный формат ответа OpenAI-совместимого API")

    raise AIError(f"Неизвестный AI_PROVIDER «{settings.ai_provider}» — допустимо: openai, anthropic")


def extract_json(text: str) -> dict:
    """Достаёт JSON-объект из ответа модели (с ```-ограждениями или без)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise AIError("AI вернул ответ не в формате JSON — повторите запуск")
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        raise AIError("Не удалось разобрать JSON из ответа AI — повторите запуск")
