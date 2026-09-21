import datetime

from sqlalchemy import Date, Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DayType


class AcademicCalendarDay(Base):
    """Тип каждой даты: учебный день, выходной, праздник, каникулы."""

    __tablename__ = "academic_calendar"

    date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    day_type: Mapped[DayType] = mapped_column(Enum(DayType), nullable=False)
