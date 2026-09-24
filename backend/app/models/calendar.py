import datetime

from sqlalchemy import Date, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DayType


class AcademicCalendarDay(Base):
    """Тип каждой даты по умолчанию для всего колледжа: учебный день,
    выходной, праздник, каникулы, ЭФО. Переопределяется точечно для
    конкретной группы через GroupCalendarOverride (например, рабочая
    суббота у 1 курса)."""

    __tablename__ = "academic_calendar"

    date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    day_type: Mapped[DayType] = mapped_column(Enum(DayType), nullable=False)


class GroupCalendarOverride(Base):
    """Переопределение типа дня для конкретной группы — приоритетнее
    общего календаря (см. обновление 1.3: 1 курс учится по субботам,
    у отдельных групп бывают дни ЭФО среди недели)."""

    __tablename__ = "academic_calendar_group_override"

    study_group_id: Mapped[int] = mapped_column(
        ForeignKey("study_groups.id", ondelete="CASCADE"), primary_key=True
    )
    date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    day_type: Mapped[DayType] = mapped_column(Enum(DayType), nullable=False)
