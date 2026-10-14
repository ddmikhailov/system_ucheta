"""Сборка версии для передачи системному администратору.

В результате — архив release/kait20-<версия>.zip, в корне которого папки
backend/, frontend/ и deploy/ (конфигурации Apache/службы/резервных копий для Linux и
Windows и PDF-инструкция из docs/deploy). Никаких файлов Docker, Amvera, CI, тестов и
служебных документов репозитория в нём нет; сборка фронтенда уже лежит в
backend/static, поэтому на сервере Node не нужен.

Состав берётся из git (отслеживаемые файлы и новые неигнорируемые, текущее
состояние диска), поэтому секреты (.env), кэши и выгрузки с ФИО, которые
в .gitignore, в архив попасть не могут. После сборки результат проверяется:
лишние файлы и упоминания Docker/Amvera/контейнеров останавливают сборку.

Запуск (из корня репозитория, нужны Python и Node/npm):
    python tools/build_release.py
    python tools/build_release.py --skip-frontend-build   # взять готовый frontend/dist
"""
import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from collections.abc import Iterable
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_ROOT = REPO / "release"
INSTALL_GUIDE = REPO / "docs" / "install-guide.md"
DEPLOY_SOURCE = "docs/deploy/"
# Документ для принятия решений (не для администратора сервера) в архив не кладём; генератор PDF — тоже.
DEPLOY_EXCLUDE_BASENAMES = {"kait20-zagruzka-dannyh-varianty.pdf"}

INCLUDE_ROOTS = ("backend/", "frontend/")
EXCLUDE_PREFIXES = ("backend/tests/",)
# Тесты и помощники тестов фронтенда (рядом с кодом: *.test.ts[x], src/test/) — разработчикам, не администратору.
EXCLUDE_PATTERNS = (re.compile(r"^frontend/src/(test/|.*\.test\.tsx?$)"),)
# Имена файлов (в любой папке), которым в передаваемой версии не место.
EXCLUDE_BASENAMES = {
    "pytest.ini", "requirements-dev.in", "requirements-dev.txt",
    ".gitignore", ".gitattributes", ".dockerignore",
}
FORBIDDEN_PATH = re.compile(r"(^|/)(Dockerfile[^/]*|\.dockerignore|docker-compose[^/]*|amvera[^/]*|\.github)(/|$)", re.I)
FORBIDDEN_TEXT = re.compile(r"docker|amvera|контейнер", re.I)
REQUIRED_TOP_LEVEL = {"backend", "frontend"}
ALLOWED_TOP_LEVEL = REQUIRED_TOP_LEVEL | {"deploy"}
TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".mjs", ".css", ".html", ".json", ".md", ".txt", ".in", ".ini",
    ".toml", ".yml", ".yaml", ".mako", ".example", ".svg", ".map", ".cfg", "",
}


def select_files(paths: Iterable[str]) -> list[str]:
    """Какие из файлов репозитория (пути через /) попадают в передаваемую версию."""
    selected = []
    for path in paths:
        if not path.startswith(INCLUDE_ROOTS):
            continue
        if path.startswith(EXCLUDE_PREFIXES) or any(p.search(path) for p in EXCLUDE_PATTERNS):
            continue
        if path.rsplit("/", 1)[-1] in EXCLUDE_BASENAMES:
            continue
        if FORBIDDEN_PATH.search(path):
            continue
        selected.append(path)
    return sorted(selected)


def select_deploy_files(paths: Iterable[str]) -> list[str]:
    """Файлы docs/deploy, которые кладутся в папку deploy/ архива (плоско, по именам)."""
    return sorted(
        p for p in paths
        if p.startswith(DEPLOY_SOURCE) and "/" not in p[len(DEPLOY_SOURCE):]
        and p.rsplit("/", 1)[-1] not in DEPLOY_EXCLUDE_BASENAMES
    )


def find_problems(root: Path) -> list[str]:
    """Что в собранной папке не должно быть: лишние верхнеуровневые папки/файлы,
    запрещённые имена файлов и упоминания Docker/Amvera/контейнеров в тексте."""
    problems: list[str] = []
    top_level = {entry.name for entry in root.iterdir()}
    if not REQUIRED_TOP_LEVEL <= top_level or not top_level <= ALLOWED_TOP_LEVEL:
        problems.append(
            f"в корне должно быть ровно {sorted(REQUIRED_TOP_LEVEL)} (и по желанию deploy), а там {sorted(top_level)}"
        )

    for file in sorted(root.rglob("*")):
        if not file.is_file():
            continue
        relative = file.relative_to(root).as_posix()
        if FORBIDDEN_PATH.search(relative):
            problems.append(f"запрещённое имя файла: {relative}")
            continue
        if file.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        match = FORBIDDEN_TEXT.search(text)
        if match:
            line_no = text.count("\n", 0, match.start()) + 1
            problems.append(f"упоминание «{match.group(0)}» в {relative}:{line_no}")
    return problems


def tracked_and_new_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPO, capture_output=True, check=True,
    )
    return [p for p in result.stdout.decode("utf-8").split("\0") if p]


def uncommitted_changes() -> list[str]:
    result = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, check=True)
    return result.stdout.decode("utf-8").splitlines()


def backend_version() -> str:
    pyproject = tomllib.loads((REPO / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    return pyproject["project"]["version"]


def build_frontend() -> None:
    npm = shutil.which("npm")
    if npm is None:
        sys.exit("Не найден npm — нужен для сборки фронтенда (или используйте --skip-frontend-build).")
    for command in (["ci"], ["run", "build"]):
        subprocess.run([npm, *command], cwd=REPO / "frontend", check=True)


def assemble(destination: Path, files: list[str], deploy_files: list[str] | None = None) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    for relative in files:
        source = REPO / relative
        if not source.is_file():  # tracked, но удалён с диска
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    dist = REPO / "frontend" / "dist"
    if not (dist / "index.html").is_file():
        sys.exit("Нет frontend/dist/index.html — соберите фронтенд (убрав --skip-frontend-build).")
    shutil.copytree(dist, destination / "backend" / "static")

    for relative in deploy_files or []:
        source = REPO / relative
        if source.is_file():
            target = destination / "deploy" / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def make_zip(source_dir: Path, archive: Path) -> str:
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(p for p in source_dir.rglob("*") if p.is_file()):
            zf.write(file, file.relative_to(source_dir).as_posix())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name + ".sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-frontend-build", action="store_true", help="не пересобирать фронтенд, взять frontend/dist")
    args = parser.parse_args()

    dirty = uncommitted_changes()
    if dirty:
        print(f"ВНИМАНИЕ: в репозитории {len(dirty)} незакоммиченных изменений — сборка возьмёт текущее состояние диска.")

    if not args.skip_frontend_build:
        build_frontend()

    version = backend_version()
    all_files = tracked_and_new_files()
    files = select_files(all_files)
    deploy_files = select_deploy_files(all_files)
    if not any(p.endswith("kait20-instrukciya-administratoru.pdf") for p in deploy_files):
        print("ВНИМАНИЕ: в docs/deploy нет PDF-инструкции — соберите её (python tools/build_deploy_pdf.py) и добавьте в git.")
    destination = OUT_ROOT / f"kait20-{version}"
    assemble(destination, files, deploy_files)

    problems = find_problems(destination)
    if problems:
        print("СБОРКА ОСТАНОВЛЕНА — в передаваемой версии найдено лишнее:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        raise SystemExit(1)

    archive = OUT_ROOT / f"kait20-{version}.zip"
    digest = make_zip(destination, archive)
    if INSTALL_GUIDE.is_file():
        shutil.copyfile(INSTALL_GUIDE, OUT_ROOT / f"kait20-{version}-INSTALL.md")

    count = sum(1 for p in destination.rglob("*") if p.is_file())
    print(f"Готово: {archive} ({archive.stat().st_size / 1024 / 1024:.1f} МБ, файлов: {count})")
    print(f"Папка для проверки: {destination}")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
