import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


class StudentMyId(Base):
    """Вкладка «Мой ID» (раздел «Моя группа»): у студента на учебный год — зарегистрирована ли биометрия «Мой.ID»,
    есть ли он сам и его родитель в чатах MAX, и причины, если нет. `None` — ещё не заполнено, `True` — «ДА»,
    `False` — «НЕТ» (как в таблице, которую кураторы вели в Excel). Причина хранится только при «НЕТ»."""

    __tablename__ = "student_my_id"
    __table_args__ = (UniqueConstraint("student_id", "school_year", name="uq_student_my_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    school_year: Mapped[str] = mapped_column(String(9), nullable=False)  # «2026-2027»
    biometrics: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    biometrics_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    max_student: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    max_student_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    max_parent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    max_parent_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
