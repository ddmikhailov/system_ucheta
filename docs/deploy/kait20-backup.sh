#!/bin/bash
# Ежедневная резервная копия БД платформы. Запуск из cron от пользователя kait20:
#   30 2 * * *  /opt/kait20/kait20-backup.sh
# Учётные данные БД берутся из ~/.my.cnf пользователя kait20 (права 600),
# чтобы пароль не светился в списке процессов:
#   [client]
#   user=kait20
#   password=...
set -euo pipefail
DEST=/var/backups/kait20
KEEP_DAYS=30
mkdir -p "$DEST"
STAMP=$(date +%Y%m%d-%H%M)
mysqldump --single-transaction --no-tablespaces --routines --triggers \
  --default-character-set=utf8mb4 kait20 | gzip > "$DEST/kait20-$STAMP.sql.gz"
# Проверка, что архив читается и в нём есть данные (пустой дамп — тоже сбой).
gzip -t "$DEST/kait20-$STAMP.sql.gz"
test "$(zcat "$DEST/kait20-$STAMP.sql.gz" | grep -c 'CREATE TABLE')" -ge 20
find "$DEST" -name 'kait20-*.sql.gz' -mtime +"$KEEP_DAYS" -delete
echo "OK: $DEST/kait20-$STAMP.sql.gz"
