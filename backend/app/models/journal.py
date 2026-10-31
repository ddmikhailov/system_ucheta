import datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


class LessonMark(Base):
    """Ячейка электронного журнала преподавателя (оценка или «н»), загруженная из выгрузки журнала.

    Это отдельная запись «как в журнале преподавателя»: она не меняет дневные отметки посещаемости куратора
    (их ставит куратор в «Сдать день», причину пропуска знает он), а используется для сверки и успеваемости.
    Столбец журнала — один академический час; `slot` — его порядковый номер среди часов того же дня."""

    __tablename__ = "lesson_marks"
    __table_args__ = (UniqueConstraint("student_id", "subject_code", "date", "slot", name="uq_lesson_mark"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_code: Mapped[str] = mapped_column(String(32), nullable=False)  # «МДК.01.01»
    subject_name: Mapped[str] = mapped_column(String(255), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 2–5
    absent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # «н»
    imported_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    imported_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class JournalLesson(Base):
    """Столбец журнала дисциплины: дата, час, тема и домашнее задание. Нужен, чтобы показать журнал целиком
    (часы без отметок тоже видны) и тему урока. Журнал общий для групп из подписи выгрузки — `group_key`
    хранит их коды (`,са1112,са2112.9,`), по нему журнал находят из группы."""

    __tablename__ = "journal_lessons"
    __table_args__ = (UniqueConstraint("subject_code", "group_key", "date", "slot", name="uq_journal_lesson"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    subject_name: Mapped[str] = mapped_column(String(255), nullable=False)
    group_key: Mapped[str] = mapped_column(String(255), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    homework: Mapped[str | None] = mapped_column(String(500), nullable=True)
