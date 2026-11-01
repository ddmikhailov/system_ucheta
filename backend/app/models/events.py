import datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


class GroupEvent(Base):
    """Мероприятие плана воспитательной работы группы (этап 9): пункт плана «наименование · дата · ответственные ·
    цель · результат» в одном из разделов бланка колледжа. Классный час — мероприятие с отметкой присутствующих,
    из которого делается протокол."""

    __tablename__ = "group_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_group_id: Mapped[int] = mapped_column(ForeignKey("study_groups.id"), nullable=False, index=True)
    school_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)  # «2026-2027»
    section: Mapped[str] = mapped_column(String(32), nullable=False)  # ключ раздела плана (group_event_service.SECTIONS)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    event_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    time_text: Mapped[str | None] = mapped_column(String(32), nullable=True)  # «14:30» или «1 пара»
    responsible: Mapped[str | None] = mapped_column(String(255), nullable=True)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="planned", server_default="planned")
    result: Mapped[str | None] = mapped_column(Text, nullable=True)  # «Отметка о выполнении / результат»
    is_class_hour: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # формат и описание проведения (для протокола)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class GroupEventAttendee(Base):
    """Присутствовавший на мероприятии (классном часе) студент."""

    __tablename__ = "group_event_attendees"

    event_id: Mapped[int] = mapped_column(ForeignKey("group_events.id", ondelete="CASCADE"), primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), primary_key=True)


class ParentMeeting(Base):
    """Родительское собрание группы (этап 10): повестка, участники, «слушали / постановили», явка родителей.
    Из него делается протокол в Word; число собраний и явка — основа для отчёта куратора."""

    __tablename__ = "parent_meetings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_group_id: Mapped[int] = mapped_column(ForeignKey("study_groups.id"), nullable=False, index=True)
    school_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)  # номер собрания в учебном году
    meeting_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    agenda: Mapped[str | None] = mapped_column(Text, nullable=True)  # по одному вопросу в строке
    staff: Mapped[str | None] = mapped_column(Text, nullable=True)  # сотрудники колледжа: «ФИО, должность», по одному в строке
    speakers: Mapped[str | None] = mapped_column(Text, nullable=True)  # приглашённые спикеры, по одному в строке
    meeting_format: Mapped[str] = mapped_column(String(16), nullable=False, default="in_person", server_default="in_person")
    parents_count: Mapped[int | None] = mapped_column(Integer, nullable=True)  # если поимённо не отмечали
    listened: Mapped[str | None] = mapped_column(Text, nullable=True)  # «Слушали»
    resolved: Mapped[str | None] = mapped_column(Text, nullable=True)  # «Постановили»
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ParentMeetingAttendee(Base):
    """Родитель / законный представитель, присутствовавший на собрании."""

    __tablename__ = "parent_meeting_attendees"

    meeting_id: Mapped[int] = mapped_column(ForeignKey("parent_meetings.id", ondelete="CASCADE"), primary_key=True)
    guardian_id: Mapped[int] = mapped_column(ForeignKey("student_guardians.id", ondelete="CASCADE"), primary_key=True)


class GroupAssembly(Base):
    """Общее собрание студентов группы (п. 5.1.10 положения о кураторе): повестка, председатель и секретарь,
    «слушали / постановили». Из него делается протокол в Word; поимённой явки нет — только число присутствовавших."""

    __tablename__ = "group_assemblies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_group_id: Mapped[int] = mapped_column(ForeignKey("study_groups.id"), nullable=False, index=True)
    school_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)  # номер собрания в учебном году
    assembly_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    chair: Mapped[str | None] = mapped_column(String(255), nullable=True)  # председатель
    secretary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    present_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agenda: Mapped[str | None] = mapped_column(Text, nullable=True)  # по одному вопросу в строке
    listened: Mapped[str | None] = mapped_column(Text, nullable=True)  # «Слушали»
    resolved: Mapped[str | None] = mapped_column(Text, nullable=True)  # «Постановили»
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class CuratorReport(Base):
    """Отчёт куратора за семестр (этап 8): то, что куратор внёс или поправил вручную (задолженности, стипендии, ИУП,
    движение контингента, ВКУ …). Остальное платформа считает сама при просмотре и выгрузке; `values_json` — JSON
    «ключ показателя → текст», пустое значение не хранится."""

    __tablename__ = "curator_reports"
    __table_args__ = (UniqueConstraint("study_group_id", "school_year", "semester", name="uq_curator_report"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_group_id: Mapped[int] = mapped_column(ForeignKey("study_groups.id"), nullable=False, index=True)
    school_year: Mapped[str] = mapped_column(String(9), nullable=False)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 — сентябрь–январь, 2 — февраль–август
    values_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class SafetyInstruction(Base):
    """Запись журнала инструктажа по охране труда (п. 5.1.15 положения): дата, вид, тема, кто провёл. Подписи студентов
    ставятся на бумаге: платформа печатает бланк с полным списком группы на день печати."""

    __tablename__ = "safety_instructions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_group_id: Mapped[int] = mapped_column(ForeignKey("study_groups.id"), nullable=False, index=True)
    school_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)
    instruction_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # introductory / primary / repeated / targeted / unplanned
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    conducted_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
