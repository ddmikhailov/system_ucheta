import datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base
from app.models.enums import BasisStatus, MarkSource


class MarkCode(Base):
    """Справочник кодов посещаемости с флагами поведения."""

    __tablename__ = "mark_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(4), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    counts_as_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_excused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_document: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DaySubmission(Base):
    """Факт сдачи дня по группе."""

    __tablename__ = "day_submissions"
    __table_args__ = (UniqueConstraint("study_group_id", "date", name="uq_day_submission"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_group_id: Mapped[int] = mapped_column(ForeignKey("study_groups.id"), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    submitted_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    submitted_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    is_on_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    study_group: Mapped["StudyGroup"] = relationship()
    submitted_by: Mapped["User"] = relationship()


class AttendanceMark(Base):
    """Отметка: студент, дата, код, автор, время — журнал, а не матрица."""

    __tablename__ = "attendance_marks"
    __table_args__ = (UniqueConstraint("student_id", "date", name="uq_student_date_mark"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    mark_code_id: Mapped[int] = mapped_column(ForeignKey("mark_codes.id"), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[MarkSource] = mapped_column(
        Enum(MarkSource), nullable=False, default=MarkSource.MANUAL
    )
    absence_period_id: Mapped[int | None] = mapped_column(
        ForeignKey("absence_periods.id"), nullable=True
    )

    # Основание: номер и дата приказа / дата заявления / реквизиты справки.
    basis_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    basis_status: Mapped[BasisStatus] = mapped_column(
        Enum(BasisStatus), nullable=False, default=BasisStatus.NOT_REQUIRED
    )

    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    student: Mapped["Student"] = relationship()
    mark_code: Mapped["MarkCode"] = relationship()
    absence_period: Mapped["AbsencePeriod"] = relationship(back_populates="generated_marks")


class AbsencePeriod(Base):
    """Длительный период отсутствия: студент, с даты по дату, код, основание."""

    __tablename__ = "absence_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    mark_code_id: Mapped[int] = mapped_column(ForeignKey("mark_codes.id"), nullable=False)
    date_from: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    date_to: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    basis_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    student: Mapped["Student"] = relationship()
    mark_code: Mapped["MarkCode"] = relationship()
    generated_marks: Mapped[list["AttendanceMark"]] = relationship(
        back_populates="absence_period"
    )
