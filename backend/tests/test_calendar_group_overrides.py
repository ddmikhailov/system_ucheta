"""Обновление 1.3: 1 курс учится по субботам (остальные — нет), плюс
точечные исключения календаря для конкретной группы (например, ЭФО)."""
import datetime

from app.models import DayType, GroupCalendarOverride
from app.services import calendar_service


def test_saturday_is_study_day_for_course_1(test_engine, db):
    saturday = datetime.date(2026, 9, 26)
    assert saturday.weekday() == 5
    assert calendar_service.is_study_day(db, saturday, course=1) is True


def test_saturday_is_weekend_for_other_courses(test_engine, db):
    saturday = datetime.date(2026, 9, 26)
    assert calendar_service.is_study_day(db, saturday, course=2) is False


def test_group_override_takes_priority_over_default(test_engine, db, imported):
    from app.models import StudyGroup

    group = db.query(StudyGroup).filter(StudyGroup.course == 2).first()
    wednesday = datetime.date(2026, 9, 23)
    assert wednesday.weekday() == 2

    assert calendar_service.is_study_day(db, wednesday, study_group_id=group.id) is True

    db.add(GroupCalendarOverride(study_group_id=group.id, date=wednesday, day_type=DayType.REMOTE))
    db.commit()

    assert calendar_service.is_study_day(db, wednesday, study_group_id=group.id) is True
    assert calendar_service.resolve_day_type(db, wednesday, study_group_id=group.id) == DayType.REMOTE

    # У других групп в этот день исключения нет — обычный учебный день, не ЭФО.
    other_group = db.query(StudyGroup).filter(StudyGroup.course == 2, StudyGroup.id != group.id).first()
    assert calendar_service.resolve_day_type(db, wednesday, study_group_id=other_group.id) == DayType.STUDY_DAY


def test_group_override_can_make_saturday_study_day_for_non_first_course(test_engine, db, imported):
    from app.models import StudyGroup

    group = db.query(StudyGroup).filter(StudyGroup.course == 3).first()
    saturday = datetime.date(2026, 9, 26)

    assert calendar_service.is_study_day(db, saturday, study_group_id=group.id, course=group.course) is False

    db.add(GroupCalendarOverride(study_group_id=group.id, date=saturday, day_type=DayType.STUDY_DAY))
    db.commit()

    assert calendar_service.is_study_day(db, saturday, study_group_id=group.id, course=group.course) is True


def test_api_upsert_and_delete_group_override(client, admin_headers, imported, db):
    from app.models import StudyGroup

    group = db.query(StudyGroup).first()
    date_str = "2026-10-03"

    r = client.put(
        "/admin/calendar/group-overrides", headers=admin_headers,
        json={"study_group_id": group.id, "date": date_str, "day_type": "remote"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["day_type"] == "remote"

    r = client.get(
        f"/admin/calendar/group-overrides?study_group_id={group.id}&date_from=2026-10-01&date_to=2026-10-31",
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert any(row["date"] == date_str for row in r.json())

    r = client.delete(
        f"/admin/calendar/group-overrides?study_group_id={group.id}&date={date_str}", headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    r = client.get(
        f"/admin/calendar/group-overrides?study_group_id={group.id}&date_from=2026-10-01&date_to=2026-10-31",
        headers=admin_headers,
    )
    assert r.json() == []


def test_curator_cannot_set_group_override(client, curator_headers, curator_group):
    r = client.put(
        "/admin/calendar/group-overrides", headers=curator_headers,
        json={"study_group_id": curator_group.id, "date": "2026-10-03", "day_type": "remote"},
    )
    assert r.status_code == 403
