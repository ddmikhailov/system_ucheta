import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


class GroupSubject(Base):
    """Дисциплина группы и её преподаватель: справочник куратора (п. 5.1.5 положения).

    Код («МДК.01.01») необязателен: по нему журнал дисциплины находит свою строку, а без кода куратор
    просто ведёт список. Телефон преподавателя — служебный контакт, не данные студента, поэтому не шифруется."""

    __tablename__ = "group_subjects"
    __table_args__ = (UniqueConstraint("study_group_id", "code", name="uq_group_subject_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_group_id: Mapped[int] = mapped_column(ForeignKey("study_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    teacher_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    teacher_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
