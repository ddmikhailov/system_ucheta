import datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


class StudentMeal(Base):
    """Явный выбор куратора «питается / не питается». Нет записи — студент питается (по умолчанию)."""

    __tablename__ = "student_meals"

    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), primary_key=True)
    eats: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class MealSubmission(Base):
    """Еженедельная подача куратора: сколько питающихся группа заказывает на каждый учебный день недели."""

    __tablename__ = "meal_submissions"
    __table_args__ = (UniqueConstraint("study_group_id", "week_start", name="uq_meal_submission_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_group_id: Mapped[int] = mapped_column(ForeignKey("study_groups.id"), nullable=False, index=True)
    week_start: Mapped[datetime.date] = mapped_column(Date, nullable=False)  # понедельник недели, на которую подано
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    submitted_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class MealDayOverride(Base):
    """Число на конкретный день, отличное от недельного: правка куратора до 10:00 предыдущего учебного дня
    либо «замороженное» значение уже закрытого дня при повторной подаче недели."""

    __tablename__ = "meal_day_overrides"
    __table_args__ = (UniqueConstraint("study_group_id", "date", name="uq_meal_override_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_group_id: Mapped[int] = mapped_column(ForeignKey("study_groups.id"), nullable=False, index=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    edited_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    edited_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
