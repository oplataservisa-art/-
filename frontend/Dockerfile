# Frontend: сборка статики и раздача через Nginx (reverse proxy для API).
# Контекст сборки — корень репозитория (см. docker-compose.yml).
FROM node:20-alpine AS build
WORKDIR /app
# Только воспроизводимая сборка: npm ci требует package-lock.json.
# Если lock-файла нет, сборка упадёт на COPY — сгенерируйте его один раз
# в окружении с доступом к npm-реестру и закоммитьте:
#   cd frontend && npm install --package-lock-only
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/index.html frontend/vite.config.js ./
COPY frontend/src ./src
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -q -O /dev/null http://localhost/ || exit 1
