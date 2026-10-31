import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base


class UrgentReport(Base):
    """Срочное сообщение куратора заведующему о проступке, правонарушении или ЧП со студентом (п. 3.1.26 положения).
    Текст шифруется, как особые поля досье, а в колокольчик не попадает. Строки удаляются вместе со студентом."""

    __tablename__ = "urgent_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # misconduct — проступок, offense — правонарушение, emergency — ЧП
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    text_enc: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    acknowledged_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    student: Mapped["Student"] = relationship()  # noqa: F821
    author: Mapped["User"] = relationship(foreign_keys=[author_id])  # noqa: F821
    acknowledged_by: Mapped["User | None"] = relationship(foreign_keys=[acknowledged_by_user_id])  # noqa: F821
