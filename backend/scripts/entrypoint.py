"""Запуск платформы: дождаться базу, накатить миграции, засеять справочники,
при явном включении — импортировать «Диджитал», и только потом поднять
приложение. Достаточно задать переменные окружения (или файл .env рядом) —
больше ничего вручную выполнять не нужно.

Миграции и справочники идут отдельными процессами, а не вызовом изнутри:
alembic/env.py вызывает logging.config.fileConfig(), который в общем
процессе отключил бы логи приложения. В конце на Linux процесс заменяется на
uvicorn (os.execvp) — он сам получает сигналы остановки; на Windows exec
процесс не заменяет, поэтому там uvicorn запускается дочерним, а скрипт ждёт
его и возвращает его код выхода.

Переменные: PORT (по умолчанию 8000), HOST (по умолчанию 0.0.0.0; если перед
приложением стоит обратный прокси на том же сервере — задайте 127.0.0.1),
IMPORT_ON_START и IMPORT_DATA_DIR (разовый импорт).

Запуск (из папки backend): python -m scripts.entrypoint
"""
import os
import re
import subprocess
import sys
import time
import tomllib
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from pathlib import Path

DB_WAIT_SECONDS = 180
DB_RETRY_INTERVAL_SECONDS = 3
IS_WINDOWS = os.name == "nt"
PERSISTENT_IMPORT_DIR = Path("/data/import")
IMPORT_FILES = ("students.csv", "curators.csv", "groups.csv")
REGISTRY_FILE = "registry.xlsx"
ATTENDANCE_FILE = "attendance.xlsx"
CURATORS_FILE_PREFIX = "curators_"  # curators_<Отделение>.tsv
CURATORS_UNIFIED_FILE = "curators.tsv"  # ФИО, группа, отделение
PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def load_env_file(path: Path | None = None, environ: MutableMapping[str, str] = os.environ) -> bool:
    """Значения из файла .env (рядом с запуском, как его читает и само приложение)
    попадают в окружение процесса — иначе их не увидели бы ни создание
    администратора (ADMIN_PASSWORD), ни разовый импорт, ни этот скрипт
    (PORT, HOST). Уже заданные переменные окружения важнее файла. Возвращает
    False, если файла нет."""
    from dotenv import dotenv_values

    env_file = path or Path.cwd() / ".env"
    if not env_file.is_file():
        return False
    for key, value in dotenv_values(env_file, encoding="utf-8").items():
        if value is not None and key not in environ:
            environ[key] = value
    return True


def log(message: str) -> None:
    print(f"[entrypoint] {message}", flush=True)


def check_python_version(
    version_info: Sequence[int] = sys.version_info, pyproject: Path = PYPROJECT
) -> None:
    """Версия Python берётся из requires-python в pyproject.toml (">=3.12,<3.15": проверены 3.12, 3.13 и 3.14).
    На другой версии зависимости из lock-файла могут не встать или повести себя
    иначе, поэтому на сервере лучше остановиться сразу и понятно."""
    if not pyproject.is_file():
        return
    spec = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {}).get("requires-python")
    if not spec:
        return
    low = re.search(r">=\s*(\d+)\.(\d+)", spec)
    high = re.search(r"<\s*(\d+)\.(\d+)", spec)
    current = (version_info[0], version_info[1])
    too_old = low is not None and current < (int(low[1]), int(low[2]))
    too_new = high is not None and current >= (int(high[1]), int(high[2]))
    if too_old or too_new:
        wanted = f"{low[1]}.{low[2]}" if low else "подходящая"
        if low and high:
            wanted += f"–{high[1]}.{int(high[2]) - 1}"
        print(
            f"[entrypoint] Требуется Python {spec}, а запущен {current[0]}.{current[1]}. Нужна версия {wanted}.",
            file=sys.stderr, flush=True,
        )
        raise SystemExit(1)


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


def default_import_dir() -> str:
    """Постоянное хранилище /data/import, если оно есть на сервере, иначе папка
    scripts/import/data рядом с кодом (туда же кладёт выгрузки README)."""
    if PERSISTENT_IMPORT_DIR.is_dir():
        return str(PERSISTENT_IMPORT_DIR)
    return str(Path(__file__).resolve().parent / "import" / "data")


def import_data_dir_if_enabled(environ: Mapping[str, str]) -> str | None:
    """Импорт «Диджитал» — разовая ручная операция, а не то, что должно
    повторяться при каждом запуске (каждый раз заново
    создавались бы уже удалённые/переименованные студенты, а кураторы
    получали бы второе назначение на группу). Включается явно
    IMPORT_ON_START=true только на тот один деплой, где он нужен, и сразу
    выключается обратно. Возвращает папку с выгрузками, если импорт нужно
    выполнить, иначе None."""
    if environ.get("IMPORT_ON_START", "false") != "true":
        log("IMPORT_ON_START не включён — импорт пропущен (это нормально после первого раза).")
        return None
    import_dir = environ.get("IMPORT_DATA_DIR") or default_import_dir()
    if not all(os.path.isfile(os.path.join(import_dir, name)) for name in IMPORT_FILES):
        log(f"IMPORT_ON_START=true, но выгрузки в {import_dir} не найдены — импорт пропущен.")
        return None
    log(f"IMPORT_ON_START=true — импорт «Диджитал» из {import_dir}...")
    return import_dir


def registry_file_if_enabled(environ: Mapping[str, str]) -> str | None:
    """Загрузка реестра контингента (scripts.import_registry) — тоже разовая:
    включается IMPORT_REGISTRY_ON_START=true на один запуск и выключается
    обратно. Файл registry.xlsx лежит в той же папке, что и выгрузки импорта.
    Возвращает путь к файлу или None."""
    if environ.get("IMPORT_REGISTRY_ON_START", "false") != "true":
        return None
    import_dir = environ.get("IMPORT_DATA_DIR") or default_import_dir()
    path = os.path.join(import_dir, REGISTRY_FILE)
    if not os.path.isfile(path):
        log(f"IMPORT_REGISTRY_ON_START=true, но файла {path} нет — загрузка реестра пропущена.")
        return None
    log(f"IMPORT_REGISTRY_ON_START=true — загрузка реестра из {path}...")
    return path


def attendance_import_if_enabled(environ: Mapping[str, str]) -> tuple[str, bool] | None:
    """Актуализация посещаемости из attendance.xlsx (scripts.import_attendance_xlsx):
    IMPORT_ATTENDANCE_ON_START=dry — пробный прогон (отчёт в логах, ничего не пишется),
    =true — запись со стиранием старых отметок. Разовая: после запуска переменную убрать.
    Возвращает (путь, записывать ли) или None."""
    mode = environ.get("IMPORT_ATTENDANCE_ON_START", "false")
    if mode not in ("dry", "true"):
        return None
    import_dir = environ.get("IMPORT_DATA_DIR") or default_import_dir()
    search_dirs = [import_dir]
    if Path(import_dir) == PERSISTENT_IMPORT_DIR:
        search_dirs.append(str(PERSISTENT_IMPORT_DIR.parent))  # файл могли положить прямо в /data
    path = next((c for c in (os.path.join(d, ATTENDANCE_FILE) for d in search_dirs) if os.path.isfile(c)), os.path.join(import_dir, ATTENDANCE_FILE))
    if not os.path.isfile(path):
        log(f"IMPORT_ATTENDANCE_ON_START={mode}, но файла {ATTENDANCE_FILE} нет в {', '.join(search_dirs)} — актуализация посещаемости пропущена.")
        return None
    log(f"IMPORT_ATTENDANCE_ON_START={mode} — посещаемость из {path} ({'запись' if mode == 'true' else 'пробный прогон'})...")
    return path, mode == "true"


def schedule_import_if_enabled(environ: Mapping[str, str]) -> tuple[list[str], bool] | None:
    """Заполнение «к какой паре пришла группа» из выгрузок расписания
    (scripts.import_first_period_schedule): xlsx лежат прямо в /data (или в папке
    импорта), можно и в подпапке schedule; attendance.xlsx и registry.xlsx — не
    расписание, их пропускаем. IMPORT_SCHEDULE_ON_START=dry — пробный прогон,
    =true — запись (только пустые пары). Разовая: после запуска переменную убрать.
    Возвращает (файлы, записывать ли) или None."""
    mode = environ.get("IMPORT_SCHEDULE_ON_START", "false")
    if mode not in ("dry", "true"):
        return None
    import_dir = environ.get("IMPORT_DATA_DIR") or default_import_dir()
    folders = [import_dir, os.path.join(import_dir, "schedule")]
    if Path(import_dir) == PERSISTENT_IMPORT_DIR:
        folders += [str(PERSISTENT_IMPORT_DIR.parent), str(PERSISTENT_IMPORT_DIR.parent / "schedule")]
    skip = {ATTENDANCE_FILE, REGISTRY_FILE}
    files = sorted({
        os.path.join(folder, name)
        for folder in folders if os.path.isdir(folder)
        for name in os.listdir(folder)
        if name.endswith(".xlsx") and name not in skip and not name.startswith("~$")
    })
    if not files:
        log(f"IMPORT_SCHEDULE_ON_START={mode}, но xlsx-файлов расписания нет в {', '.join(folders)} — заполнение пар пропущено.")
        return None
    log(f"IMPORT_SCHEDULE_ON_START={mode} — расписание, файлов: {len(files)} ({'запись' if mode == 'true' else 'пробный прогон'})...")
    return files, mode == "true"


def curator_lists_if_enabled(environ: Mapping[str, str]) -> list[tuple[str, str | None]]:
    """Списки кураторов (scripts.import_curators): единый curators.tsv с
    колонкой отделения и/или файлы curators_<Отделение>.tsv рядом с выгрузками
    импорта. Включается разово IMPORT_CURATORS_ON_START=true. Возвращает пары
    (путь, отделение или None, если отделение указано в самом файле)."""
    if environ.get("IMPORT_CURATORS_ON_START", "false") != "true":
        return []
    import_dir = environ.get("IMPORT_DATA_DIR") or default_import_dir()
    found: list[tuple[str, str | None]] = []
    if os.path.isdir(import_dir):
        unified = os.path.join(import_dir, CURATORS_UNIFIED_FILE)
        if os.path.isfile(unified):
            found.append((unified, None))
        for name in sorted(os.listdir(import_dir)):
            if name.startswith(CURATORS_FILE_PREFIX) and name.endswith(".tsv"):
                found.append((os.path.join(import_dir, name), name[len(CURATORS_FILE_PREFIX):-len(".tsv")]))
    if not found:
        log(f"IMPORT_CURATORS_ON_START=true, но файла {CURATORS_UNIFIED_FILE} в {import_dir} нет.")
    return found


def main(environ: Mapping[str, str] = os.environ) -> None:
    check_python_version()

    # Настройки читаем сразу: неверный/слабый JWT_SECRET и прочее
    # останавливают запуск с понятным сообщением до всех остальных шагов.
    from app.core.config import get_settings

    settings = get_settings()

    # Ключ шифрования особых полей досье: без него эти поля недоступны (остальное работает),
    # а испорченный ключ лучше поймать на старте, чем при первой записи.
    from app.core import field_crypto

    if not settings.dossier_encryption_key:
        log("ВНИМАНИЕ: DOSSIER_ENCRYPTION_KEY не задан — особые поля досье (здоровье, соц. статус) недоступны.")
    elif not field_crypto.is_available():
        raise SystemExit("DOSSIER_ENCRYPTION_KEY некорректен: нужен ключ Fernet (см. .env.example).")

    log(f"Ожидание базы данных {settings.db_host}:{settings.db_port}...")
    wait_for_database(_connect_to_database)

    log("Миграции...")
    run_step("-m", "alembic", "upgrade", "head")

    log("Справочники...")
    run_step("-m", "scripts.seed")

    import_dir = import_data_dir_if_enabled(environ)
    if import_dir is not None:
        run_step("-m", "scripts.import_source_data", env={**environ, "IMPORT_DATA_DIR": import_dir})

    registry_path = registry_file_if_enabled(environ)
    if registry_path is not None:
        run_step("-m", "scripts.import_registry", registry_path, "--apply")

    curator_lists = curator_lists_if_enabled(environ)
    for curators_path, department in curator_lists:
        log(f"Кураторы: {department or os.path.basename(curators_path)}...")
        run_step("-m", "scripts.import_curators", curators_path, *([department] if department else []), "--apply")

    # Группы со строчной «о» в коде нигде не учитываются: скрываем их после
    # реестра — иначе загрузка реестра вернула бы их в работу.
    if registry_path is not None or curator_lists:
        log("Скрытие групп со строчной «о» в коде...")
        run_step("-m", "scripts.hide_groups", "--apply")

    attendance = attendance_import_if_enabled(environ)
    if attendance is not None:
        attendance_path, commit = attendance
        run_step("-m", "scripts.import_attendance_xlsx", attendance_path, *(["--commit"] if commit else []))

    schedule = schedule_import_if_enabled(environ)
    if schedule is not None:
        schedule_files, commit = schedule
        run_step("-m", "scripts.import_first_period_schedule", *schedule_files, *(["--commit"] if commit else []))

    log("Запуск приложения...")
    port = str(int(environ.get("PORT") or "8000"))
    host = environ.get("HOST") or "0.0.0.0"
    command = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", host, "--port", port]
    if IS_WINDOWS:
        raise SystemExit(subprocess.run(command).returncode)
    os.execvp(command[0], command)


if __name__ == "__main__":
    load_env_file()
    main()
