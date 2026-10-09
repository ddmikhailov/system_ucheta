"""Объявленные версии не расходятся: приложение, Python, Node и lock-файлы.
Тест нужен, потому что единого источника правды нет (backend и frontend
собираются раздельно) — расхождение иначе всплыло бы только на сервере."""
import json
import re
import sys
import tomllib
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
FRONTEND = REPO / "frontend"


def _pyproject():
    return tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def _pins(path: Path) -> dict[str, str]:
    """name==version из .in / lock-файла (без extras, регистр не важен)."""
    pins = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?==([^\s;\\]+)", line)
        if match:
            pins[match[1].lower().replace("_", "-")] = match[2]
    return pins


def test_app_version_is_the_same_everywhere():
    main_version = re.search(r'version="([^"]+)"', (BACKEND / "app" / "main.py").read_text(encoding="utf-8"))[1]
    assert _pyproject()["version"] == main_version
    if FRONTEND.is_dir():
        assert json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))["version"] == main_version


def test_running_python_satisfies_requires_python():
    spec = _pyproject()["requires-python"]
    low = re.search(r">=\s*(\d+)\.(\d+)", spec)
    high = re.search(r"<\s*(\d+)\.(\d+)", spec)
    current = sys.version_info[:2]
    assert current >= (int(low[1]), int(low[2]))
    assert current < (int(high[1]), int(high[2]))


def test_python_version_file_matches_requires_python():
    declared = (BACKEND / ".python-version").read_text(encoding="utf-8").strip()
    low = re.search(r">=\s*(\d+\.\d+)", _pyproject()["requires-python"])[1]
    assert declared == low


@pytest.mark.skipif(not (REPO / "Dockerfile").is_file(), reason="Dockerfile есть только в репозитории, не в образе")
def test_dockerfile_base_images_match_declared_versions():
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    python_tag = re.search(r"^FROM python:(\d+\.\d+)", dockerfile, re.M)[1]
    # Образ может быть новее минимальной версии (облако на 3.14, сервер колледжа на 3.12), но обязан входить в поддерживаемый диапазон.
    spec = _pyproject()["requires-python"]
    low = re.search(r">=\s*(\d+)\.(\d+)", spec)
    high = re.search(r"<\s*(\d+)\.(\d+)", spec)
    tag = tuple(int(x) for x in python_tag.split("."))
    assert (int(low[1]), int(low[2])) <= tag < (int(high[1]), int(high[2]))

    node_major = re.search(r"^FROM node:(\d+)", dockerfile, re.M)[1]
    assert node_major == (FRONTEND / ".nvmrc").read_text(encoding="utf-8").strip()


@pytest.mark.skipif(not FRONTEND.is_dir(), reason="нет каталога frontend")
def test_node_version_file_satisfies_declared_engine():
    engine = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))["engines"]["node"]
    minimum_major = int(re.search(r">=\s*(\d+)", engine)[1])
    assert int((FRONTEND / ".nvmrc").read_text(encoding="utf-8").strip()) >= minimum_major
    assert "engine-strict=true" in (FRONTEND / ".npmrc").read_text(encoding="utf-8")


@pytest.mark.parametrize("source, lock", [("requirements.in", "requirements.txt"), ("requirements-dev.in", "requirements-dev.txt")])
def test_lock_file_contains_every_pinned_dependency_with_the_same_version(source, lock):
    """Поправили версию в .in и забыли пересобрать lock — на сервер поедет старая."""
    wanted = _pins(BACKEND / source)
    locked = _pins(BACKEND / lock)
    assert wanted, f"в {source} нет ни одной закреплённой зависимости"
    for name, version in wanted.items():
        assert locked.get(name) == version, f"{name}: в {source} {version}, в {lock} {locked.get(name)} — пересоберите lock"


@pytest.mark.parametrize("lock", ["requirements.txt", "requirements-dev.txt"])
def test_every_locked_package_has_hashes(lock):
    text = (BACKEND / lock).read_text(encoding="utf-8")
    blocks = re.split(r"\n(?=[A-Za-z0-9_.\-]+(?:\[[^\]]*\])?==)", text)
    packages = [b for b in blocks if re.match(r"[A-Za-z0-9_.\-]+(?:\[[^\]]*\])?==", b)]
    assert packages
    unhashed = [b.split("==")[0] for b in packages if "--hash=sha256:" not in b]
    assert not unhashed, f"без хэша: {unhashed}"
