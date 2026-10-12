"""Реестр выключаемых модулей (релиз 3.5.0): разбор ENABLED_MODULES."""
import pytest

from app.core.config import get_settings
from app.core.modules import ALL_MODULES, RELEASE_MODULES, enabled_modules, module_enabled, parse_modules


def test_empty_value_is_release_set():
    assert parse_modules("") == frozenset(RELEASE_MODULES)
    assert RELEASE_MODULES == ("attendance", "tasks", "my_id", "meals")


def test_value_is_normalized_and_attendance_is_always_on():
    assert parse_modules(" Tasks , MEALS ") == frozenset({"attendance", "tasks", "meals"})


def test_all_enables_every_module():
    assert parse_modules("all") == frozenset(ALL_MODULES)
    assert len(ALL_MODULES) == 10


def test_unknown_name_is_startup_error_naming_the_typo():
    with pytest.raises(RuntimeError, match="passprt"):
        parse_modules("tasks,passprt")


def test_module_enabled_follows_settings(monkeypatch):
    monkeypatch.setattr(get_settings(), "enabled_modules", "meals")
    assert module_enabled("meals")
    assert module_enabled("attendance")
    assert not module_enabled("tasks")
    assert enabled_modules() == frozenset({"attendance", "meals"})
