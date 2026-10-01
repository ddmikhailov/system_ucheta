"""tools/build_release.py — состав версии для передачи администратору."""
import importlib.util
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent.parent / "tools" / "build_release.py"
pytestmark = pytest.mark.skipif(not TOOL.is_file(), reason="инструмента сборки нет вне репозитория")


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("build_release", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_select_files_keeps_only_backend_and_frontend_code(tool):
    paths = [
        "backend/app/main.py", "backend/alembic/env.py", "backend/requirements.txt", "backend/requirements.in",
        "backend/pyproject.toml", "backend/.env.example", "backend/scripts/entrypoint.py",
        "frontend/src/App.tsx", "frontend/package.json", "frontend/index.html",
        # лишнее:
        "backend/tests/test_api_admin.py", "backend/pytest.ini", "backend/requirements-dev.txt",
        "backend/requirements-dev.in", "frontend/.gitignore",
        "Dockerfile", "docker-compose.yml", "amvera.yml", ".dockerignore", ".github/workflows/ci.yml",
        "README.md", "TODO.md", "CHANGELOG.md", "futures.md", ".gitignore", "tools/build_release.py",
    ]
    selected = tool.select_files(paths)

    assert selected == sorted([
        "backend/app/main.py", "backend/alembic/env.py", "backend/requirements.txt", "backend/requirements.in",
        "backend/pyproject.toml", "backend/.env.example", "backend/scripts/entrypoint.py",
        "frontend/src/App.tsx", "frontend/package.json", "frontend/index.html",
    ])


def test_select_files_drops_docker_and_amvera_files_even_inside_backend_or_frontend(tool):
    paths = ["backend/Dockerfile", "backend/docker-compose.override.yml", "frontend/amvera.yml", "frontend/.dockerignore",
             "backend/app/ok.py"]
    assert tool.select_files(paths) == ["backend/app/ok.py"]


def _tree(tmp_path, files):
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


def test_find_problems_accepts_a_clean_tree(tool, tmp_path):
    _tree(tmp_path, {"backend/app/main.py": "print('привет')\n", "frontend/src/App.tsx": "export {}\n"})
    assert tool.find_problems(tmp_path) == []


def test_find_problems_reports_extra_top_level_entries(tool, tmp_path):
    _tree(tmp_path, {"backend/a.py": "x\n", "frontend/b.ts": "x\n", "README.md": "x\n"})
    assert any("в корне должно быть ровно" in p for p in tool.find_problems(tmp_path))


def test_find_problems_reports_forbidden_files_and_text_mentions(tool, tmp_path):
    _tree(tmp_path, {
        "backend/app/main.py": "# запускается в Docker\n",
        "backend/note.md": "строка\nна Amvera\n",
        "backend/scripts/seed.py": "print('пересоздайте контейнер')\n",
        "frontend/Dockerfile": "FROM node\n",
    })
    problems = "\n".join(tool.find_problems(tmp_path))

    assert "упоминание «Docker» в backend/app/main.py:1" in problems
    assert "упоминание «Amvera» в backend/note.md:2" in problems
    assert "упоминание «контейнер» в backend/scripts/seed.py:1" in problems
    assert "запрещённое имя файла: frontend/Dockerfile" in problems


def test_find_problems_ignores_binary_files(tool, tmp_path):
    _tree(tmp_path, {"backend/a.py": "x\n", "frontend/b.ts": "x\n"})
    (tmp_path / "frontend" / "logo.webp").write_bytes(b"RIFF\x00docker\xff")
    assert tool.find_problems(tmp_path) == []
