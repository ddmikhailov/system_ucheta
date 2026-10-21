import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base


class StudentDeletionRequest(Base):
    """Запрос куратора на полное удаление студента. Стирание необратимо, поэтому его делает только
    администратор, тьютор или зав. отделением группы студента — после одобрения запроса.
    Строки запроса удаляются вместе со студентом (причина может содержать ПДн)."""

    __tablename__ = "student_deletion_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    requested_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    # pending → approved / rejected / cancelled (отозван автором)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    review_comment: Mapped[str | None] = mapped_column(String(500), nullable=True)

    student: Mapped["Student"] = relationship()  # noqa: F821
    requested_by: Mapped["User"] = relationship(foreign_keys=[requested_by_user_id])  # noqa: F821
