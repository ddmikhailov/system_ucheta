"""Правило общих перечней: учитываются все активные группы (с куратором и без),
отключённая группа (is_active = false) в них не попадает."""
from app.models import StudyGroup
from app.services import stats_service, summary_service

VACANT = "ИИ132"  # в тестовой выгрузке — вакансия, куратора нет


def codes(rows):
    return {r["code"] for r in rows}


def set_active(db, code, active):
    db.query(StudyGroup).filter_by(code=code).one().is_active = active
    db.commit()


def test_vacant_active_group_is_counted(imported, db, today):
    assert VACANT in codes(stats_service.day_overview(db, today))
    assert VACANT in codes(stats_service.curator_discipline(db, today, today))
    assert len(stats_service.day_overview(db, today)) == 44


def test_disabled_group_leaves_every_general_list(imported, db, today):
    set_active(db, "ИИ112", False)

    assert "ИИ112" not in codes(stats_service.day_overview(db, today))
    assert "ИИ112" not in codes(stats_service.curator_discipline(db, today, today))
    assert "ИИ112" not in {r.group_code for r in summary_service.collect_group_day_rows(db, today, today)}
    assert len(stats_service.day_overview(db, today)) == 43


def test_group_returns_to_the_lists_when_enabled_again(imported, db, today):
    set_active(db, "ИИ112", False)
    set_active(db, "ИИ112", True)

    assert "ИИ112" in codes(stats_service.day_overview(db, today))
