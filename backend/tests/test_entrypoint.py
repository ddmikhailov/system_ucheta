"""scripts/entrypoint.py — замена docker-entrypoint.sh: порядок шагов запуска,
ожидание базы, условия разового импорта и остановка при сбое шага."""
import subprocess
import sys

import pytest

from scripts import entrypoint


class _FakeConnection:
    def close(self):
        pass


class _Clock:
    """Время, которое двигает только sleep, — без реального ожидания."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_wait_for_database_retries_until_available(capsys):
    clock = _Clock()
    attempts = []

    def connect():
        attempts.append(1)
        if len(attempts) < 3:
            raise ConnectionError("ещё не поднялась")
        return _FakeConnection()

    entrypoint.wait_for_database(connect, timeout=60, interval=3, sleep=clock.sleep, clock=clock)

    assert len(attempts) == 3
    assert clock.now == 6  # два ожидания по 3 секунды
    assert "База доступна" in capsys.readouterr().out


def test_wait_for_database_gives_up_with_last_error(capsys):
    clock = _Clock()

    def connect():
        raise ConnectionError("отказано в соединении")

    with pytest.raises(SystemExit) as exc:
        entrypoint.wait_for_database(connect, timeout=10, interval=3, sleep=clock.sleep, clock=clock)

    assert exc.value.code == 1
    assert "отказано в соединении" in capsys.readouterr().err


@pytest.fixture()
def recorded(monkeypatch):
    """Подменяет ожидание базы, запуск шагов и exec — ничего реального не стартует."""
    calls = {"steps": [], "exec": None}
    monkeypatch.setattr(entrypoint, "wait_for_database", lambda connect: None)

    def fake_run(args, check, env):
        calls["steps"].append((args[1:], env))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(entrypoint.subprocess, "run", fake_run)
    monkeypatch.setattr(entrypoint.os, "execvp", lambda file, argv: calls.__setitem__("exec", (file, argv)))
    return calls


def test_main_runs_migrations_then_seed_then_starts_uvicorn(recorded):
    entrypoint.main({"PORT": "9000"})

    assert [step for step, _ in recorded["steps"]] == [
        ["-m", "alembic", "upgrade", "head"],
        ["-m", "scripts.seed"],
    ]
    file, argv = recorded["exec"]
    assert file == sys.executable
    assert argv[1:] == ["-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]


def test_main_defaults_to_port_8000(recorded):
    entrypoint.main({})
    assert recorded["exec"][1][-1] == "8000"


def test_main_rejects_a_non_numeric_port_before_exec(recorded):
    with pytest.raises(ValueError):
        entrypoint.main({"PORT": "abc"})
    assert recorded["exec"] is None


def test_import_runs_only_when_enabled_and_all_files_exist(recorded, tmp_path):
    for name in entrypoint.IMPORT_FILES:
        (tmp_path / name).write_text("x", encoding="utf-8")

    entrypoint.main({"IMPORT_ON_START": "true", "IMPORT_DATA_DIR": str(tmp_path)})

    steps = recorded["steps"]
    assert [s for s, _ in steps][-1] == ["-m", "scripts.import_source_data"]
    assert steps[-1][1]["IMPORT_DATA_DIR"] == str(tmp_path)
    assert recorded["exec"] is not None


def test_import_skipped_when_not_enabled(recorded, tmp_path):
    for name in entrypoint.IMPORT_FILES:
        (tmp_path / name).write_text("x", encoding="utf-8")

    entrypoint.main({"IMPORT_ON_START": "false", "IMPORT_DATA_DIR": str(tmp_path)})

    assert ["-m", "scripts.import_source_data"] not in [s for s, _ in recorded["steps"]]


def test_import_skipped_when_files_are_missing(recorded, tmp_path):
    (tmp_path / "students.csv").write_text("x", encoding="utf-8")  # curators.csv и groups.csv нет

    entrypoint.main({"IMPORT_ON_START": "true", "IMPORT_DATA_DIR": str(tmp_path)})

    assert ["-m", "scripts.import_source_data"] not in [s for s, _ in recorded["steps"]]
    assert recorded["exec"] is not None  # приложение всё равно стартует


def test_failed_migration_stops_startup_with_its_exit_code(monkeypatch, recorded):
    def failing_run(args, check, env):
        recorded["steps"].append((args[1:], env))
        raise subprocess.CalledProcessError(3, args)

    monkeypatch.setattr(entrypoint.subprocess, "run", failing_run)

    with pytest.raises(SystemExit) as exc:
        entrypoint.main({})

    assert exc.value.code == 3
    assert len(recorded["steps"]) == 1  # справочники уже не запускались
    assert recorded["exec"] is None  # и приложение не стартовало
