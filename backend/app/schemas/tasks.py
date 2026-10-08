import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

CollectMode = Literal["group", "student", "selected"]
ReviewerRule = Literal["dept_head", "edu_department", "two_step", "author", "none"]
FieldType = Literal["text", "number", "date", "bool", "select", "multiselect", "link"]


class FieldDef(BaseModel):
    key: str | None = Field(default=None, max_length=40)
    label: str = Field(min_length=1, max_length=200)
    type: FieldType
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=100)
    # Поле досье, которое наполняется принятыми ответами (см. services/task_dossier.py).
    dossier_field: str | None = Field(default=None, max_length=40)


class ScopeDef(BaseModel):
    """Кому адресована задача: объединение выбранного минус исключённые группы."""

    all_groups: bool = False
    department_ids: list[int] = Field(default_factory=list)
    courses: list[int] = Field(default_factory=list)
    group_ids: list[int] = Field(default_factory=list)
    exclude_group_ids: list[int] = Field(default_factory=list)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    collect_mode: CollectMode
    reviewer_rule: ReviewerRule = "dept_head"
    due_date: datetime.date
    fields: list[FieldDef] = Field(default_factory=list, max_length=30)
    scope: ScopeDef
    # Следующий шаг многошаговой задачи: охват и группы берутся у предыдущего шага (scope игнорируется).
    after_task_id: int | None = None
    unlock_on: Literal["submitted", "accepted"] = "accepted"


class TemplateCreate(BaseModel):
    task_id: int
    name: str | None = Field(default=None, max_length=255)


class ScheduleIn(BaseModel):
    repeat: Literal["", "monthly", "semester"]
    repeat_day: int = Field(default=1, ge=1, le=28)
    due_offset_days: int = Field(default=14, ge=1, le=120)


class TemplateRead(BaseModel):
    id: int
    name: str
    author_name: str | None
    created_at: datetime.datetime
    can_manage: bool
    title: str
    description: str | None
    collect_mode: str
    reviewer_rule: str
    fields: list[FieldDef]
    scope: ScopeDef
    repeat: str
    repeat_day: int
    due_offset_days: int
    next_run: datetime.date | None
    last_run_date: datetime.date | None
    last_error: str | None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    due_date: datetime.date | None = None
    is_closed: bool | None = None


class Progress(BaseModel):
    total: int
    new: int
    in_progress: int
    submitted: int
    returned: int
    accepted: int
    overdue: int


class TaskListRow(BaseModel):
    id: int
    title: str
    collect_mode: str
    reviewer_rule: str
    due_date: datetime.date
    is_closed: bool
    author_id: int | None = None
    author_name: str | None
    progress: Progress
    step_no: int = 1
    step_total: int | None = None  # None — одиночная задача


class AssignmentSummary(BaseModel):
    id: int
    study_group_id: int
    group_code: str
    course: int
    department_name: str
    status: str
    is_overdue: bool
    submitted_at: datetime.datetime | None
    reviewed_at: datetime.datetime | None
    reviewed_by_name: str | None
    is_locked: bool = False


class StepRef(BaseModel):
    id: int
    title: str
    step_no: int
    due_date: datetime.date


class TaskDetail(BaseModel):
    id: int
    title: str
    description: str | None
    collect_mode: str
    reviewer_rule: str
    due_date: datetime.date
    is_closed: bool
    author_id: int | None
    author_name: str | None
    fields: list[FieldDef]
    scope: ScopeDef
    can_manage: bool
    progress: Progress
    assignments: list[AssignmentSummary]
    step_no: int = 1
    unlock_on: str | None = None
    steps: list[StepRef] = Field(default_factory=list)  # пусто для одиночной задачи


class MyAssignmentRow(BaseModel):
    id: int
    task_id: int
    title: str
    collect_mode: str
    group_code: str
    due_date: datetime.date
    status: str
    is_overdue: bool
    is_closed: bool
    is_locked: bool = False
    step_no: int = 1
    step_total: int | None = None
    # Заполненность: поля (ответ по группе) или студенты (остальные режимы); см. task_service.fill_progress.
    filled: int = 0
    total: int = 0
    review_comment: str | None = None
    kind: str | None = None  # "meal" — «Подать питание»


class RowRead(BaseModel):
    student_id: int
    student_name: str
    is_included: bool
    values: dict[str, Any]
    # Строка ещё не сохранялась, значения подставлены из досье — куратору достаточно проверить.
    from_dossier: bool = False


class CommentRead(BaseModel):
    id: int
    student_id: int | None
    author_name: str | None
    text: str
    created_at: datetime.datetime


class HistoryEvent(BaseModel):
    """Событие хода проверки: отправлено / принято / возвращено / принято без проверки."""

    kind: str  # submitted / accepted / returned / auto_accepted
    user_name: str | None
    at: datetime.datetime
    step: int | None = None  # ступень проверки (только при двухступенчатой)


class AssignmentDetail(BaseModel):
    id: int
    task_id: int
    title: str
    description: str | None
    collect_mode: str
    reviewer_rule: str
    due_date: datetime.date
    is_closed: bool
    fields: list[FieldDef]
    study_group_id: int
    group_code: str
    status: str
    is_overdue: bool
    group_values: dict[str, Any]
    rows: list[RowRead]
    comments: list[CommentRead]
    review_comment: str | None
    submitted_at: datetime.datetime | None
    reviewed_at: datetime.datetime | None
    reviewed_by_name: str | None
    history: list[HistoryEvent]
    review_step: int  # текущая ступень проверки
    review_steps: int  # всего ступеней: 2 для two_step, иначе 1
    can_edit: bool
    can_submit: bool
    can_review: bool
    is_locked: bool = False
    locked_reason: str | None = None
    step_no: int = 1
    step_total: int | None = None
    kind: str | None = None  # "meal" — «Подать питание»: ответ даётся во вкладке «Питание» группы


class RowIn(BaseModel):
    student_id: int
    is_included: bool = True
    values: dict[str, Any] = Field(default_factory=dict)


class AnswersIn(BaseModel):
    group_values: dict[str, Any] = Field(default_factory=dict)
    rows: list[RowIn] = Field(default_factory=list)


class ReviewIn(BaseModel):
    action: Literal["accept", "return"]
    comment: str | None = Field(default=None, max_length=2000)


class CommentIn(BaseModel):
    student_id: int | None = None
    text: str = Field(min_length=1, max_length=2000)


class ReviewQueueRow(BaseModel):
    id: int
    task_id: int
    title: str
    group_code: str
    department_name: str
    due_date: datetime.date
    submitted_at: datetime.datetime | None
    is_overdue: bool


class RemindResult(BaseModel):
    sent: int
    skipped: int


class SummaryCount(BaseModel):
    label: str
    count: int


class SummaryField(BaseModel):
    key: str
    label: str
    type: str
    filled: int
    counts: list[SummaryCount]


class TaskSummary(BaseModel):
    """Сводка отправленных ответов: groups — сколько групп отправили, answers — сколько строк (или групп)."""
    groups: int
    answers: int
    fields: list[SummaryField]


class ScopePreview(BaseModel):
    """Охват до создания задачи: группы, студенты, кураторы и группы без куратора (по коду)."""
    groups: int
    students: int
    curators: int
    without_curator: list[str]
