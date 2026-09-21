import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcademicCalendarDay, DayType


def is_study_day(db: Session, day: datetime.date) -> bool:
    row = db.get(AcademicCalendarDay, day)
    if row is not None:
        return row.day_type == DayType.STUDY_DAY
    # Календарь не заполнен на эту дату — по умолчанию будни считаем учебными днями.
    return day.weekday() < 5


def study_days_between(db: Session, date_from: datetime.date, date_to: datetime.date) -> list[datetime.date]:
    if date_from > date_to:
        return []
    rows = db.execute(
        select(AcademicCalendarDay).where(
            AcademicCalendarDay.date >= date_from, AcademicCalendarDay.date <= date_to
        )
    ).scalars().all()
    known = {row.date: row.day_type for row in rows}

    days = []
    current = date_from
    one_day = datetime.timedelta(days=1)
    while current <= date_to:
        day_type = known.get(current)
        if day_type is not None:
            if day_type == DayType.STUDY_DAY:
                days.append(current)
        elif current.weekday() < 5:
            days.append(current)
        current += one_day
    return days


def previous_study_day(db: Session, day: datetime.date, max_lookback: int = 30) -> datetime.date | None:
    current = day - datetime.timedelta(days=1)
    for _ in range(max_lookback):
        if is_study_day(db, current):
            return current
        current -= datetime.timedelta(days=1)
    return None
