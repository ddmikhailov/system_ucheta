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
    author_name: str | None
    progress: Progress


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


class RowRead(BaseModel):
    student_id: int
    student_name: str
    is_included: bool
    values: dict[str, Any]


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
