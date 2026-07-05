#!/usr/bin/env bash
# Smoke-test после запуска: проверяет health, вход, продление сессии
# и доступность основных списков. Данные НЕ изменяет.
#
# Использование:
#   ./scripts/smoke_test.sh                 # адрес http://localhost, креды из .env
#   BASE_URL=https://host ./scripts/smoke_test.sh
set -u

BASE_URL="${BASE_URL:-http://localhost}"

# Креды администратора: из окружения или из .env рядом с проектом
if [ -z "${ADMIN_EMAIL:-}" ] || [ -z "${ADMIN_PASSWORD:-}" ]; then
  ENV_FILE="$(dirname "$0")/../.env"
  if [ -f "$ENV_FILE" ]; then
    ADMIN_EMAIL="${ADMIN_EMAIL:-$(grep -E '^ADMIN_EMAIL=' "$ENV_FILE" | cut -d= -f2-)}"
    ADMIN_PASSWORD="${ADMIN_PASSWORD:-$(grep -E '^ADMIN_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)}"
  fi
fi

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  [OK]   $1"; }
fail() { FAIL=$((FAIL+1)); echo "  [FAIL] $1"; }

echo "Smoke-test: $BASE_URL"

# 1. Health backend и базы
HEALTH=$(curl -s -m 10 "$BASE_URL/api/health")
echo "$HEALTH" | grep -q '"status": *"ok"' \
  && ok "health: backend и база отвечают" \
  || fail "health: $HEALTH"

# 2. Вход администратора
if [ -z "${ADMIN_EMAIL:-}" ] || [ -z "${ADMIN_PASSWORD:-}" ]; then
  fail "вход: ADMIN_EMAIL/ADMIN_PASSWORD не заданы (окружение или .env)"
else
  TOKEN=$(curl -s -m 10 -X POST "$BASE_URL/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
    | sed -n 's/.*"access_token": *"\([^"]*\)".*/\1/p')
  if [ -n "$TOKEN" ]; then
    ok "вход администратора"

    AUTH="Authorization: Bearer $TOKEN"

    # 3. Текущий пользователь
    curl -s -m 10 -H "$AUTH" "$BASE_URL/api/auth/me" | grep -q '"email"' \
      && ok "auth/me" || fail "auth/me"

    # 4. Продление сессии
    curl -s -m 10 -X POST -H "$AUTH" "$BASE_URL/api/auth/refresh" \
      | grep -q '"access_token"' \
      && ok "auth/refresh (продление сессии)" || fail "auth/refresh"

    # 5. Основные списки (редакционный процесс, только чтение)
    for EP in sources topics articles info-events knowledge dashboard; do
      CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' -H "$AUTH" "$BASE_URL/api/$EP")
      [ "$CODE" = "200" ] && ok "GET /api/$EP" || fail "GET /api/$EP → $CODE"
    done

    # 6. Календарь за текущую неделю
    FROM=$(date +%F)
    TO=$(date -d '+7 days' +%F 2>/dev/null || date -v+7d +%F)
    CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' -H "$AUTH" \
      "$BASE_URL/api/calendar?date_from=$FROM&date_to=$TO")
    [ "$CODE" = "200" ] && ok "GET /api/calendar" || fail "GET /api/calendar → $CODE"


    # 8. Этап 3: промпты и AI-off режим (ключ не задан — сервис работает,
    #    AI-действия отвечают понятной ошибкой, ничего не ломая)
    CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' -H "$AUTH" "$BASE_URL/api/prompts")
    [ "$CODE" = "200" ] && ok "GET /api/prompts (сид промптов на месте)" || fail "GET /api/prompts → $CODE"

    STATUS_BODY=$(curl -s -m 10 -H "$AUTH" "$BASE_URL/api/ai/status")
    echo "$STATUS_BODY" | grep -q '"configured"' \
      && ok "GET /api/ai/status отвечает" || fail "GET /api/ai/status: $STATUS_BODY"

    if echo "$STATUS_BODY" | grep -q '"configured":false'; then
      # без ключа генерация должна вернуть 503 с текстом «AI не настроен»
      AI_CODE=$(curl -s -m 10 -o /tmp/ai_off.json -w '%{http_code}' -X POST \
        -H "$AUTH" -H 'Content-Type: application/json' -d '{"overwrite":false}' \
        "$BASE_URL/api/ai/articles/999999/draft")
      if [ "$AI_CODE" = "503" ] && grep -q "AI не настроен" /tmp/ai_off.json; then
        ok "AI-off: генерация отвечает 503 «AI не настроен»"
      elif [ "$AI_CODE" = "404" ]; then
        ok "AI-off: маршрут AI жив (статья не найдена — 404)"
      else
        fail "AI-off: ожидался 503, получен $AI_CODE ($(cat /tmp/ai_off.json))"
      fi
    else
      ok "AI настроен (configured:true) — off-режим не проверяется"
    fi


    # 9. Этап 4a: мониторинг — endpoint'ы живы, worker выключен по умолчанию
    CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' -H "$AUTH" "$BASE_URL/api/source-items")
    [ "$CODE" = "200" ] && ok "GET /api/source-items" || fail "GET /api/source-items → $CODE"

    CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' -H "$AUTH" "$BASE_URL/api/sources-stats")
    [ "$CODE" = "200" ] && ok "GET /api/sources-stats" || fail "GET /api/sources-stats → $CODE"

    CODE=$(curl -s -m 30 -o /dev/null -w '%{http_code}' -X POST -H "$AUTH" \
      -H 'Content-Type: application/json' -d '{}' "$BASE_URL/api/sources/999999/check-now")
    [ "$CODE" = "404" ] && ok "check-now несуществующего источника → 404" \
      || fail "check-now/999999 → $CODE (ожидался 404)"


    # 10. Этап 4b: массовые действия, тема из материалов, AI-анализ группы
    CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' -X POST -H "$AUTH" \
      -H 'Content-Type: application/json' -d '{"item_ids":[999999],"action":"hide"}' \
      "$BASE_URL/api/source-items/bulk")
    [ "$CODE" = "404" ] && ok "bulk по несуществующим материалам → 404" || fail "bulk → $CODE"

    CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' -X POST -H "$AUTH" \
      -H 'Content-Type: application/json' -d '{"item_ids":[999999]}' \
      "$BASE_URL/api/topics/from-items")
    [ "$CODE" = "404" ] && ok "topics/from-items по несуществующим → 404" || fail "topics/from-items → $CODE"

    AN_CODE=$(curl -s -m 10 -o /tmp/an_off.json -w '%{http_code}' -X POST -H "$AUTH" \
      -H 'Content-Type: application/json' -d '{"item_ids":[1]}' \
      "$BASE_URL/api/source-items/analyze-group")
    if [ "$AN_CODE" = "503" ] && grep -q "AI не настроен" /tmp/an_off.json; then
      ok "analyze-group в AI-off → 503 «AI не настроен»"
    elif [ "$AN_CODE" = "404" ] || [ "$AN_CODE" = "502" ] || [ "$AN_CODE" = "200" ]; then
      ok "analyze-group отвечает (AI настроен: $AN_CODE)"
    else
      fail "analyze-group → $AN_CODE"
    fi

    # 7. Без токена API закрыт
    CODE=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$BASE_URL/api/articles")
    [ "$CODE" = "401" ] && ok "без токена API возвращает 401" \
      || fail "без токена ожидался 401, получен $CODE"
  else
    fail "вход администратора (проверьте ADMIN_EMAIL/ADMIN_PASSWORD)"
  fi
fi

echo "Итог: OK=$PASS, FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
