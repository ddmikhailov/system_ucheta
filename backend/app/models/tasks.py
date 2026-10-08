import datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base


class Task(Base):
    """Задача от администрации (этап 3). Форма ответа и охват хранятся
    JSON-ом в самой задаче: разные задачи = разные формы без миграций БД."""

    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("template_id", "period_key", name="uq_task_template_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    collect_mode: Mapped[str] = mapped_column(String(16), nullable=False)  # group / student / selected
    reviewer_rule: Mapped[str] = mapped_column(String(24), nullable=False)  # dept_head / edu_department / author / none
    due_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fields_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    scope_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    # Периодические задачи: из какого шаблона и за какой период («2026-10») создана; на пару стоит уникальность.
    template_id: Mapped[int | None] = mapped_column(ForeignKey("task_templates.id"), nullable=True)
    period_key: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Многошаговая задача — цепочка задач с общим series_id (= id первого шага). Следующий шаг открывается
    # для группы, когда её предыдущий шаг сдан (unlock_on="submitted") или принят ("accepted").
    series_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    step_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    unlock_on: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Особый вид задачи: "meal" — «Подать питание на след. неделю»; пусто — обычная задача.
    kind: Mapped[str | None] = mapped_column(String(16), nullable=True)

    author: Mapped["User"] = relationship()
    assignments: Mapped[list["TaskAssignment"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class TaskTemplate(Base):
    """Шаблон задачи: всё, кроме срока (его задают при запуске). Виден всем, кто создаёт задачи;
    удалить может автор или администратор."""

    __tablename__ = "task_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # title, description, collect_mode, reviewer_rule, fields, scope — как в TaskCreate, без due_date
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    # Расписание (см. services/task_schedule.py): "" — не повторять, monthly, semester.
    repeat: Mapped[str] = mapped_column(String(16), nullable=False, default="", server_default="")
    repeat_day: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    due_offset_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14, server_default="14")
    next_run: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    last_run_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    author: Mapped["User | None"] = relationship()


class TaskAssignment(Base):
    """Экземпляр задачи для одной группы: свой статус, свои ответы, своя проверка."""

    __tablename__ = "task_assignments"
    __table_args__ = (UniqueConstraint("task_id", "study_group_id", name="uq_task_assignment_group"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    study_group_id: Mapped[int] = mapped_column(ForeignKey("study_groups.id"), nullable=False, index=True)
    # new / in_progress / submitted / returned / accepted
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    group_values_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Двухступенчатая проверка (reviewer_rule=two_step): 1 — зав. отделением, 2 — воспитательный отдел.
    review_step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Шаг ещё закрыт: предыдущий шаг цепочки у этой группы не сдан/не принят.
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    task: Mapped["Task"] = relationship(back_populates="assignments")
    reviewer: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by])
    study_group: Mapped["StudyGroup"] = relationship()
    rows: Mapped[list["TaskRow"]] = relationship(back_populates="assignment", cascade="all, delete-orphan")
    comments: Mapped[list["TaskComment"]] = relationship(back_populates="assignment", cascade="all, delete-orphan")


class TaskRow(Base):
    """Ответ по студенту (режимы «по каждому» и «по выбранным»)."""

    __tablename__ = "task_rows"
    __table_args__ = (UniqueConstraint("assignment_id", "student_id", name="uq_task_row_student"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("task_assignments.id"), nullable=False, index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    is_included: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    values_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    assignment: Mapped["TaskAssignment"] = relationship(back_populates="rows")


class TaskComment(Base):
    """Комментарий к назначению целиком (student_id пусто) или к строке студента."""

    __tablename__ = "task_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("task_assignments.id"), nullable=False, index=True)
    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id"), nullable=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    assignment: Mapped["TaskAssignment"] = relationship(back_populates="comments")
    author: Mapped["User"] = relationship()
