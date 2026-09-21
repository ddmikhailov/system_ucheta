import datetime

from app.models import AcademicCalendarDay, DayType
from app.services import calendar_service


def test_weekday_is_study_day_by_default(test_engine, db):
    monday = datetime.date(2026, 9, 21)
    assert monday.weekday() == 0
    assert calendar_service.is_study_day(db, monday) is True


def test_weekend_is_not_study_day_by_default(test_engine, db):
    saturday = datetime.date(2026, 9, 26)
    assert saturday.weekday() == 5
    assert calendar_service.is_study_day(db, saturday) is False


def test_calendar_exception_overrides_weekday(test_engine, db):
    holiday = datetime.date(2026, 11, 4)  # среда
    db.add(AcademicCalendarDay(date=holiday, day_type=DayType.HOLIDAY))
    db.commit()
    assert calendar_service.is_study_day(db, holiday) is False


def test_calendar_exception_can_make_weekend_a_study_day(test_engine, db):
    working_saturday = datetime.date(2026, 9, 26)
    db.add(AcademicCalendarDay(date=working_saturday, day_type=DayType.STUDY_DAY))
    db.commit()
    assert calendar_service.is_study_day(db, working_saturday) is True


def test_study_days_between_skips_weekends(test_engine, db):
    date_from = datetime.date(2026, 9, 21)  # понедельник
    date_to = datetime.date(2026, 9, 27)  # воскресенье следующей недели
    days = calendar_service.study_days_between(db, date_from, date_to)
    assert len(days) == 5
    assert all(d.weekday() < 5 for d in days)


def test_previous_study_day_skips_weekend(test_engine, db):
    monday = datetime.date(2026, 9, 21)
    prev = calendar_service.previous_study_day(db, monday)
    assert prev == datetime.date(2026, 9, 18)  # пятница
