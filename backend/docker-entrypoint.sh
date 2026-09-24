#!/bin/sh
# Запуск в контейнере: дождаться базу, накатить миграции, засеять справочники,
# при наличии выгрузок — импортировать «Диджитал», и только потом поднять
# приложение. Так деплой на PaaS не требует доступа к shell — достаточно
# задать переменные окружения.
set -e

echo "[entrypoint] Ожидание базы данных ${DB_HOST}:${DB_PORT:-3306}..."
python - <<'PY'
import os
import sys
import time

import pymysql

host = os.environ.get("DB_HOST", "db")
port = int(os.environ.get("DB_PORT", "3306"))
user = os.environ.get("DB_USER", "kait20")
password = os.environ.get("DB_PASSWORD", "")
database = os.environ.get("DB_NAME", "kait20")

deadline = time.time() + 180
last_error = None
while time.time() < deadline:
    try:
        pymysql.connect(
            host=host, port=port, user=user, password=password, database=database,
            connect_timeout=5,
        ).close()
        print("[entrypoint] База доступна.")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 — на старте важна любая причина
        last_error = exc
        time.sleep(3)

print(f"[entrypoint] База недоступна за 180 с: {last_error}", file=sys.stderr)
sys.exit(1)
PY

echo "[entrypoint] Миграции..."
alembic upgrade head

echo "[entrypoint] Справочники..."
python -m scripts.seed

# Импорт «Диджитал» — разовая ручная операция, а не то, что должно
# повторяться при каждом рестарте контейнера (см. TODO.md 1.7: раньше при
# каждом старте заново создавались уже удалённые/переименованные студенты,
# кураторы получали второе назначение на группу и т.п.). Включается явно
# переменной окружения IMPORT_ON_START=true только на тот один деплой, где
# он действительно нужен, и сразу выключается обратно.
IMPORT_DIR="${IMPORT_DATA_DIR:-/data/import}"
if [ "${IMPORT_ON_START:-false}" = "true" ]; then
    if [ -f "$IMPORT_DIR/students.csv" ] && [ -f "$IMPORT_DIR/curators.csv" ] && [ -f "$IMPORT_DIR/groups.csv" ]; then
        echo "[entrypoint] IMPORT_ON_START=true — импорт «Диджитал» из $IMPORT_DIR..."
        IMPORT_DATA_DIR="$IMPORT_DIR" python -m scripts.import_source_data
    else
        echo "[entrypoint] IMPORT_ON_START=true, но выгрузки в $IMPORT_DIR не найдены — импорт пропущен."
    fi
else
    echo "[entrypoint] IMPORT_ON_START не включён — импорт пропущен (это нормально после первого раза)."
fi

echo "[entrypoint] Запуск приложения..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
