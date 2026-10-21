"""Выключаемые модули платформы (релиз 3.5.0).

К релизу нужны посещаемость, задачи, «Мой ID», питание, досье и индивидуальная работа; остальное (соц. паспорт,
план, собрания, отчёт) скрыто, но код и данные остаются. Набор задаёт переменная `ENABLED_MODULES`
(имена через запятую или `all`); без неё включён релизный набор. Выключенный модуль: его роутеры не подключены
(404), а сквозные связи в сервисах проверяют `module_enabled(...)`.

Зеркало для интерфейса — frontend/src/constants/modules.ts: меняя список, правьте оба
(сверяет tests/test_frontend_roles_contract.py)."""
from app.core.config import get_settings

ALWAYS_ON = "attendance"
RELEASE_MODULES = ("attendance", "tasks", "my_id", "meals", "dossier", "individual_work")
HIDDEN_IN_RELEASE = ("passport", "plan", "meetings", "reports")
ALL_MODULES = RELEASE_MODULES + HIDDEN_IN_RELEASE


def parse_modules(raw: str) -> frozenset[str]:
    """Набор включённых модулей по значению ENABLED_MODULES. Пусто — релизный набор, `all` — все;
    `attendance` включён всегда. Неизвестное имя — ошибка запуска: опечатка не должна молча менять набор."""
    names = [part.strip().lower() for part in (raw or "").split(",") if part.strip()]
    if not names:
        return frozenset(RELEASE_MODULES)
    if "all" in names:
        return frozenset(ALL_MODULES)
    unknown = [n for n in names if n not in ALL_MODULES]
    if unknown:
        raise RuntimeError(
            "ENABLED_MODULES содержит неизвестные модули: " + ", ".join(unknown)
            + ". Допустимы: " + ", ".join(ALL_MODULES) + " или all."
        )
    return frozenset(names) | {ALWAYS_ON}


def enabled_modules() -> frozenset[str]:
    return parse_modules(get_settings().enabled_modules)


def module_enabled(name: str) -> bool:
    return name in enabled_modules()
