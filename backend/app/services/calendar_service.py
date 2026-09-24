import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcademicCalendarDay, DayType, GroupCalendarOverride, StudyGroup

_ATTENDABLE_TYPES = (DayType.STUDY_DAY, DayType.REMOTE)


def _course_of(db: Session, study_group_id: int | None, course: int | None) -> int | None:
    if course is not None or study_group_id is None:
        return course
    group = db.get(StudyGroup, study_group_id)
    return group.course if group else None


def _default_day_type(day: datetime.date, course: int | None) -> DayType:
    weekday = day.weekday()
    if weekday == 5:
        # Только 1 курс учится по субботам — у остальных курсов это выходной
        # (обновление 1.3), если явно не переопределено календарём.
        return DayType.STUDY_DAY if course == 1 else DayType.WEEKEND
    if weekday == 6:
        return DayType.WEEKEND
    return DayType.STUDY_DAY


def resolve_day_type(
    db: Session,
    day: datetime.date,
    study_group_id: int | None = None,
    course: int | None = None,
) -> DayType:
    if study_group_id is not None:
        override = db.get(GroupCalendarOverride, (study_group_id, day))
        if override is not None:
            return override.day_type
    global_row = db.get(AcademicCalendarDay, day)
    if global_row is not None:
        return global_row.day_type
    return _default_day_type(day, _course_of(db, study_group_id, course))


def is_study_day(
    db: Session,
    day: datetime.date,
    study_group_id: int | None = None,
    course: int | None = None,
) -> bool:
    return resolve_day_type(db, day, study_group_id, course) in _ATTENDABLE_TYPES


def study_days_between(
    db: Session,
    date_from: datetime.date,
    date_to: datetime.date,
    study_group_id: int | None = None,
    course: int | None = None,
) -> list[datetime.date]:
    if date_from > date_to:
        return []
    course = _course_of(db, study_group_id, course)

    rows = db.execute(
        select(AcademicCalendarDay).where(
            AcademicCalendarDay.date >= date_from, AcademicCalendarDay.date <= date_to
        )
    ).scalars().all()
    known = {row.date: row.day_type for row in rows}

    overrides: dict[datetime.date, DayType] = {}
    if study_group_id is not None:
        override_rows = db.execute(
            select(GroupCalendarOverride).where(
                GroupCalendarOverride.study_group_id == study_group_id,
                GroupCalendarOverride.date >= date_from,
                GroupCalendarOverride.date <= date_to,
            )
        ).scalars().all()
        overrides = {row.date: row.day_type for row in override_rows}

    days = []
    current = date_from
    one_day = datetime.timedelta(days=1)
    while current <= date_to:
        day_type = overrides.get(current) or known.get(current) or _default_day_type(current, course)
        if day_type in _ATTENDABLE_TYPES:
            days.append(current)
        current += one_day
    return days


def previous_study_day(
    db: Session,
    day: datetime.date,
    study_group_id: int | None = None,
    course: int | None = None,
    max_lookback: int = 30,
) -> datetime.date | None:
    course = _course_of(db, study_group_id, course)
    current = day - datetime.timedelta(days=1)
    for _ in range(max_lookback):
        if is_study_day(db, current, study_group_id, course):
            return current
        current -= datetime.timedelta(days=1)
    return None
