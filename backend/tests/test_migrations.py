"""Цепочка миграций Alembic: ровно одна голова.

Две головы появляются, когда ветки с новыми миграциями сливаются, а `down_revision` никто не выровнял.
Тогда `alembic upgrade head` при старте контейнера (scripts/entrypoint.py) падает и платформа не поднимается.
Тест ловит это до выкладки, на любой базе: он читает только файлы в alembic/versions.
"""
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _script_directory() -> ScriptDirectory:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(config)


def test_single_alembic_head():
    heads = _script_directory().get_heads()
    assert len(heads) == 1, f"Несколько голов миграций: {sorted(heads)}. Выровнять down_revision у новых миграций."


def test_every_revision_reachable_from_head():
    """Нет «висящих» миграций: каждая ревизия лежит на пути от головы к началу цепочки."""
    script = _script_directory()
    all_revisions = {rev.revision for rev in script.walk_revisions()}
    chain = {rev.revision for rev in script.iterate_revisions("heads", "base")}
    assert all_revisions == chain
