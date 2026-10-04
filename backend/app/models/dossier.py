import datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base


class StudentProfile(Base):
    """Досье студента: один ряд на студента. Обычные поля и контакты — колонки;
    особые категории ПДн (здоровье, соц. статус, учёт) лежат одним
    зашифрованным JSON-блобом `special_enc` (см. app/core/field_crypto.py)."""

    __tablename__ = "student_profiles"

    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), primary_key=True)
    birth_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(8), nullable=True)  # male / female; по нему склоняются документы
    funding: Mapped[str | None] = mapped_column(String(16), nullable=True)  # budget / contract
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    messenger: Mapped[str | None] = mapped_column(String(128), nullable=True)
    registration_address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    residence_address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    additional_education: Mapped[str | None] = mapped_column(String(1000), nullable=True)  # заполняют задачи
    special_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class StudentGuardian(Base):
    __tablename__ = "student_guardians"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relation: Mapped[str] = mapped_column(String(64), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class StudentNote(Base):
    """Заметка куратора: беседа, звонок, инцидент, договорённость."""

    __tablename__ = "student_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    # Журнал индивидуальной работы: когда это было (по умолчанию — день записи) и когда вернуться к вопросу.
    occurred_on: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    follow_up_on: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    follow_up_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")

    author: Mapped["User"] = relationship()


class DossierAccessLog(Base):
    """Журнал просмотров досье: кто и когда открывал, видел ли особые поля."""

    __tablename__ = "dossier_access_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    included_special: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)

    user: Mapped["User"] = relationship()
