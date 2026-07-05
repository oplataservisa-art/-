"""Конфигурация сервиса.

Все секреты берутся ТОЛЬКО из переменных окружения (см. .env.example).
В коде нет ни одного ключа или пароля — требование раздела 14.5 ТЗ.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- База данных ---
    database_url: str = "postgresql+psycopg2://effecom:change_me@db:5432/effecom"

    # --- JWT / сессии ---
    # Модель сессии: токен живёт access_token_minutes и автоматически
    # продлевается при активности (frontend вызывает /api/auth/refresh);
    # при неактивности дольше access_token_minutes сессия истекает;
    # session_max_hours — абсолютный предел, после него нужен новый вход.
    secret_key: str = "CHANGE_ME_IN_ENV"          # обязательно переопределить в .env
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60                # истечение при неактивности
    session_max_hours: int = 12                   # абсолютный предел сессии

    # --- Защита от brute force (14.2.8-9) ---
    max_failed_logins: int = 5
    lockout_minutes: int = 15

    # --- CORS allowlist (14.3.5) ---
    cors_origins: str = "http://localhost"        # список через запятую, никогда "*"

    # --- Первичный администратор (создаётся один раз при пустой таблице users) ---
    admin_email: str = "admin@effecom.ru"
    admin_password: str = "CHANGE_ME_IN_ENV"
    admin_name: str = "Администратор"

    environment: str = "development"

    # --- AI-провайдер (Этап 3, разделы 6.6-6.9 и 14.11 ТЗ) ---
    # Все настройки ТОЛЬКО из .env; ключ в коде/БД/интерфейсе не хранится.
    # ai_provider: "openai" (и любой OpenAI-совместимый API) | "anthropic" | "" (выключен)
    ai_provider: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    ai_base_url: str = ""                 # для OpenAI-совместимых (напр. локальный шлюз)
    ai_timeout_seconds: int = 120         # таймаут одного запроса (обязателен)
    ai_max_output_tokens: int = 4000
    # Лимиты стоимости (14.11.7): 0 = лимит отключён
    ai_daily_budget_usd: float = 5.0
    ai_monthly_budget_usd: float = 50.0
    # Цены модели за 1M токенов — для подсчёта расхода (14.11.8)
    ai_price_input_per_1m: float = 0.0
    ai_price_output_per_1m: float = 0.0

    # --- Мониторинг источников (Этап 4a, разделы 6.1-6.2 и 14.7 ТЗ) ---
    # По умолчанию ВЫКЛЮЧЕН: worker при false ничего не парсит.
    monitor_enabled: bool = False
    monitor_tick_seconds: int = 300          # период пробуждения воркера
    monitor_http_timeout: int = 20           # таймаут одного HTTP-запроса, сек
    monitor_max_items_per_run: int = 30      # лимит новых материалов за прогон
    monitor_user_agent: str = "EFFECOM-ContentBot/1.0 (+content-service; contact admin)"
    monitor_max_response_kb: int = 2048      # лимит размера ответа источника

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
