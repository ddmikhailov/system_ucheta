"""Запуск в контейнере: дождаться базу, накатить миграции, засеять справочники,
при явном включении — импортировать «Диджитал», и только потом поднять
приложение. Так деплой на PaaS не требует доступа к shell — достаточно
задать переменные окружения.

Заменяет прежний docker-entrypoint.sh: тот же порядок шагов, но на Python,
чтобы в проекте не осталось ничего, кроме Python и React.

Миграции и справочники идут отдельными процессами, а не вызовом изнутри:
alembic/env.py вызывает logging.config.fileConfig(), который в общем
процессе отключил бы логи приложения. В конце процесс заменяется на uvicorn
(os.execvp) — он становится PID 1 и сам получает сигналы остановки от Docker.

Запуск: python -m scripts.entrypoint
"""
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping

DB_WAIT_SECONDS = 180
DB_RETRY_INTERVAL_SECONDS = 3
DEFAULT_IMPORT_DIR = "/data/import"
IMPORT_FILES = ("students.csv", "curators.csv", "groups.csv")


def log(message: str) -> None:
    print(f"[entrypoint] {message}", flush=True)


def wait_for_database(
    connect: Callable[[], object],
    timeout: float = DB_WAIT_SECONDS,
    interval: float = DB_RETRY_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    deadline = clock() + timeout
    last_error: Exception | None = None
    while clock() < deadline:
        try:
            connect().close()  # type: ignore[attr-defined]
            log("База доступна.")
            return
        except Exception as exc:  # noqa: BLE001 — на старте важна любая причина
            last_error = exc
            sleep(interval)
    print(f"[entrypoint] База недоступна за {timeout:.0f} с: {last_error}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def _connect_to_database():
    import pymysql

    from app.core.config import get_settings

    settings = get_settings()
    return pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        connect_timeout=5,
    )


def run_step(*python_args: str, env: Mapping[str, str] | None = None) -> None:
    """Python-процесс с этими аргументами; провал шага останавливает запуск
    с тем же кодом возврата (раньше это делал `set -e`)."""
    try:
        subprocess.run([sys.executable, *python_args], check=True, env=env)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc


def import_data_dir_if_enabled(environ: Mapping[str, str]) -> str | None:
    """Импорт «Диджитал» — разовая ручная операция, а не то, что должно
    повторяться при каждом рестарте контейнера (при каждом старте заново
    создавались бы уже удалённые/переименованные студенты, а кураторы
    получали бы второе назначение на группу). Включается явно
    IMPORT_ON_START=true только на тот один деплой, где он нужен, и сразу
    выключается обратно. Возвращает папку с выгрузками, если импорт нужно
    выполнить, иначе None."""
    if environ.get("IMPORT_ON_START", "false") != "true":
        log("IMPORT_ON_START не включён — импорт пропущен (это нормально после первого раза).")
        return None
    import_dir = environ.get("IMPORT_DATA_DIR", DEFAULT_IMPORT_DIR)
    if not all(os.path.isfile(os.path.join(import_dir, name)) for name in IMPORT_FILES):
        log(f"IMPORT_ON_START=true, но выгрузки в {import_dir} не найдены — импорт пропущен.")
        return None
    log(f"IMPORT_ON_START=true — импорт «Диджитал» из {import_dir}...")
    return import_dir


def main(environ: Mapping[str, str] = os.environ) -> None:
    # Настройки читаем сразу: неверный/слабый JWT_SECRET и прочее
    # останавливают запуск с понятным сообщением до всех остальных шагов.
    from app.core.config import get_settings

    settings = get_settings()

    log(f"Ожидание базы данных {settings.db_host}:{settings.db_port}...")
    wait_for_database(_connect_to_database)

    log("Миграции...")
    run_step("-m", "alembic", "upgrade", "head")

    log("Справочники...")
    run_step("-m", "scripts.seed")

    import_dir = import_data_dir_if_enabled(environ)
    if import_dir is not None:
        run_step("-m", "scripts.import_source_data", env={**environ, "IMPORT_DATA_DIR": import_dir})

    log("Запуск приложения...")
    port = str(int(environ.get("PORT", "8000")))
    os.execvp(
        sys.executable,
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", port],
    )


if __name__ == "__main__":
    main()
