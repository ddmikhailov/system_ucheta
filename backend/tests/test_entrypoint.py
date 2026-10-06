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
    monkeypatch.setattr(entrypoint, "IS_WINDOWS", False)  # по умолчанию проверяем Linux-ветку (exec)

    def fake_run(args, check=False, env=None):
        calls["steps"].append((args[1:], env))
        return subprocess.CompletedProcess(args, calls.get("returncode", 0))

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
    def failing_run(args, check=False, env=None):
        recorded["steps"].append((args[1:], env))
        raise subprocess.CalledProcessError(3, args)

    monkeypatch.setattr(entrypoint.subprocess, "run", failing_run)

    with pytest.raises(SystemExit) as exc:
        entrypoint.main({})

    assert exc.value.code == 3
    assert len(recorded["steps"]) == 1  # справочники уже не запускались
    assert recorded["exec"] is None  # и приложение не стартовало


def _pyproject(tmp_path, spec):
    path = tmp_path / "pyproject.toml"
    path.write_text(f'[project]\nname = "x"\nversion = "0"\nrequires-python = "{spec}"\n', encoding="utf-8")
    return path


def test_python_version_inside_the_range_is_accepted(tmp_path):
    entrypoint.check_python_version((3, 14, 7), _pyproject(tmp_path, ">=3.14,<3.15"))


@pytest.mark.parametrize("version", [(3, 13, 9), (3, 15, 0), (3, 12, 1)])
def test_python_version_outside_the_range_stops_startup(tmp_path, capsys, version):
    with pytest.raises(SystemExit) as exc:
        entrypoint.check_python_version(version, _pyproject(tmp_path, ">=3.14,<3.15"))

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert ">=3.14,<3.15" in err and f"{version[0]}.{version[1]}" in err


def test_missing_pyproject_does_not_block_startup(tmp_path):
    entrypoint.check_python_version((3, 9, 0), tmp_path / "нет-такого.toml")


def test_main_checks_the_python_version_first(monkeypatch, recorded):
    monkeypatch.setattr(entrypoint, "check_python_version", lambda: (_ for _ in ()).throw(SystemExit(1)))

    with pytest.raises(SystemExit):
        entrypoint.main({})

    assert recorded["steps"] == [] and recorded["exec"] is None


def test_host_defaults_to_all_interfaces_and_can_be_overridden(recorded):
    entrypoint.main({})
    assert recorded["exec"][1][recorded["exec"][1].index("--host") + 1] == "0.0.0.0"

    recorded["exec"] = None
    entrypoint.main({"HOST": "127.0.0.1"})
    assert recorded["exec"][1][recorded["exec"][1].index("--host") + 1] == "127.0.0.1"


def test_on_windows_uvicorn_runs_as_a_child_and_its_exit_code_is_returned(monkeypatch, recorded):
    """os.execvp на Windows процесс не заменяет — служба решила бы, что запуск
    завершился. Поэтому там uvicorn дочерний, а код выхода пробрасывается."""
    monkeypatch.setattr(entrypoint, "IS_WINDOWS", True)
    recorded["returncode"] = 7

    with pytest.raises(SystemExit) as exc:
        entrypoint.main({"PORT": "9100"})

    assert exc.value.code == 7
    assert recorded["exec"] is None
    server_step = recorded["steps"][-1][0]
    assert server_step[:3] == ["-m", "uvicorn", "app.main:app"] and server_step[-1] == "9100"


def test_default_import_dir_prefers_persistent_storage_when_it_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(entrypoint, "PERSISTENT_IMPORT_DIR", tmp_path)
    assert entrypoint.default_import_dir() == str(tmp_path)


def test_default_import_dir_falls_back_to_the_folder_next_to_the_code(monkeypatch, tmp_path):
    monkeypatch.setattr(entrypoint, "PERSISTENT_IMPORT_DIR", tmp_path / "нет-такой")
    folder = entrypoint.default_import_dir()
    assert folder.replace("\\", "/").endswith("scripts/import/data")


def test_load_env_file_exports_values_but_real_environment_wins(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# комментарий\n"
        "ADMIN_PASSWORD=из-файла\n"
        'PASSWORD_WITH_SPACE="два слова"\n'
        'CORS_ORIGINS=["http://localhost:5173"]\n'
        "PORT=9999\n"
        "ALREADY_SET=из-файла\n"
        "EMPTY=\n",
        encoding="utf-8",
    )
    environ = {"ALREADY_SET": "из-окружения"}

    assert entrypoint.load_env_file(env_file, environ) is True

    assert environ["ADMIN_PASSWORD"] == "из-файла"
    assert environ["PASSWORD_WITH_SPACE"] == "два слова"
    assert environ["CORS_ORIGINS"] == '["http://localhost:5173"]'
    assert environ["PORT"] == "9999"
    assert environ["ALREADY_SET"] == "из-окружения"
    assert environ["EMPTY"] == ""


def test_load_env_file_without_a_file_changes_nothing(tmp_path):
    environ = {"A": "1"}
    assert entrypoint.load_env_file(tmp_path / "нет-такого.env", environ) is False
    assert environ == {"A": "1"}


def test_empty_port_from_env_example_style_file_falls_back_to_default(recorded):
    entrypoint.main({"PORT": ""})
    assert recorded["exec"][1][-1] == "8000"


def test_registry_import_runs_only_when_enabled_and_file_exists(recorded, tmp_path):
    (tmp_path / entrypoint.REGISTRY_FILE).write_text("x", encoding="utf-8")

    entrypoint.main({"IMPORT_REGISTRY_ON_START": "true", "IMPORT_DATA_DIR": str(tmp_path)})

    args = [s for s, _ in recorded["steps"]][-2]  # последний шаг — скрытие групп
    assert args == ["-m", "scripts.import_registry", str(tmp_path / entrypoint.REGISTRY_FILE), "--apply"]
    assert recorded["exec"] is not None


def test_registry_import_skipped_when_disabled_or_file_missing(recorded, tmp_path):
    (tmp_path / entrypoint.REGISTRY_FILE).write_text("x", encoding="utf-8")
    entrypoint.main({"IMPORT_REGISTRY_ON_START": "false", "IMPORT_DATA_DIR": str(tmp_path)})
    entrypoint.main({"IMPORT_REGISTRY_ON_START": "true", "IMPORT_DATA_DIR": str(tmp_path / "нет")})

    assert not any("scripts.import_registry" in s for s, _ in recorded["steps"])


def test_curator_lists_run_per_department_file_when_enabled(recorded, tmp_path):
    (tmp_path / "curators_Кибер.tsv").write_text("x", encoding="utf-8")
    (tmp_path / "другое.tsv").write_text("x", encoding="utf-8")

    entrypoint.main({"IMPORT_CURATORS_ON_START": "true", "IMPORT_DATA_DIR": str(tmp_path)})

    args = [s for s, _ in recorded["steps"]][-2]  # последний шаг — скрытие групп
    assert args == ["-m", "scripts.import_curators", str(tmp_path / "curators_Кибер.tsv"), "Кибер", "--apply"]


def test_curator_lists_skipped_when_disabled(recorded, tmp_path):
    (tmp_path / "curators_Кибер.tsv").write_text("x", encoding="utf-8")

    entrypoint.main({"IMPORT_CURATORS_ON_START": "false", "IMPORT_DATA_DIR": str(tmp_path)})

    assert not any("scripts.import_curators" in s for s, _ in recorded["steps"])


def test_unified_curators_file_runs_without_department_argument(recorded, tmp_path):
    (tmp_path / "curators.tsv").write_text("x", encoding="utf-8")

    entrypoint.main({"IMPORT_CURATORS_ON_START": "true", "IMPORT_DATA_DIR": str(tmp_path)})

    args = [s for s, _ in recorded["steps"]][-2]  # последний шаг — скрытие групп
    assert args == ["-m", "scripts.import_curators", str(tmp_path / "curators.tsv"), "--apply"]


def test_groups_are_hidden_after_registry_or_curators_but_not_otherwise(recorded, tmp_path):
    (tmp_path / entrypoint.REGISTRY_FILE).write_text("x", encoding="utf-8")
    entrypoint.main({"IMPORT_REGISTRY_ON_START": "true", "IMPORT_DATA_DIR": str(tmp_path)})
    assert [s for s, _ in recorded["steps"]][-1] == ["-m", "scripts.hide_groups", "--apply"]

    recorded["steps"].clear()
    entrypoint.main({"IMPORT_DATA_DIR": str(tmp_path)})
    assert not any("scripts.hide_groups" in s for s, _ in recorded["steps"])


def test_attendance_import_dry_and_commit_modes(recorded, tmp_path):
    (tmp_path / entrypoint.ATTENDANCE_FILE).write_text("x", encoding="utf-8")
    path = str(tmp_path / entrypoint.ATTENDANCE_FILE)

    entrypoint.main({"IMPORT_ATTENDANCE_ON_START": "dry", "IMPORT_DATA_DIR": str(tmp_path)})
    entrypoint.main({"IMPORT_ATTENDANCE_ON_START": "true", "IMPORT_DATA_DIR": str(tmp_path)})

    steps = [s for s, _ in recorded["steps"] if "scripts.import_attendance_xlsx" in s]
    assert steps == [
        ["-m", "scripts.import_attendance_xlsx", path],
        ["-m", "scripts.import_attendance_xlsx", path, "--commit"],
    ]


def test_attendance_import_skipped_when_disabled_or_file_missing(recorded, tmp_path):
    (tmp_path / entrypoint.ATTENDANCE_FILE).write_text("x", encoding="utf-8")
    entrypoint.main({"IMPORT_ATTENDANCE_ON_START": "false", "IMPORT_DATA_DIR": str(tmp_path)})
    entrypoint.main({"IMPORT_ATTENDANCE_ON_START": "true", "IMPORT_DATA_DIR": str(tmp_path / "нет")})

    assert not any("scripts.import_attendance_xlsx" in s for s, _ in recorded["steps"])
