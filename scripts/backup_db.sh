#!/usr/bin/env bash
# Ежедневный бэкап PostgreSQL с ротацией (блокер production №3).
# Не привязан к конкретному серверу. Запускать из корня проекта, где .env.
#
# Cron (ежедневно в 03:30):
#   30 3 * * * cd /path/to/effecom && ./scripts/backup_db.sh >> backups/backup.log 2>&1
#
# ВАЖНО: каталог с бэкапами копируйте ВНЕ сервера (s3/rsync/облако) и раз в
# месяц проверяйте восстановление на копии базы (см. README «Production»).
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

# Пользователь/база берутся из .env; дефолты совпадают с docker-compose.
POSTGRES_USER="${POSTGRES_USER:-effecom}"
POSTGRES_DB="${POSTGRES_DB:-effecom}"
if [ -f .env ]; then
  POSTGRES_USER="$(grep -E '^POSTGRES_USER=' .env | cut -d= -f2- || true)"; POSTGRES_USER="${POSTGRES_USER:-effecom}"
  POSTGRES_DB="$(grep -E '^POSTGRES_DB=' .env | cut -d= -f2- || true)"; POSTGRES_DB="${POSTGRES_DB:-effecom}"
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%F_%H%M)"
OUT="$BACKUP_DIR/effecom_${STAMP}.sql.gz"

echo "[$(date +%FT%T)] dump → $OUT"
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$OUT"

# Ротация: удалить дампы старше RETENTION_DAYS
find "$BACKUP_DIR" -name 'effecom_*.sql.gz' -type f -mtime "+$RETENTION_DAYS" -delete
echo "[$(date +%FT%T)] готово; хранение $RETENTION_DAYS дн."
