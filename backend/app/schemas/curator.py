import datetime

from pydantic import BaseModel, Field


class RosterEntry(BaseModel):
    student_id: int
    full_name: str
    mark_code: str | None
    mark_name: str | None
    comment: str | None
    basis_reference: str | None
    is_draft_suggestion: bool
    is_locked: bool
    risk_streak: int  # сколько дней подряд «н» — справочно
    attendance_percent: float | None = None  # посещаемость с начала семестра, %
    is_risk: bool = False  # группа риска: посещаемость ниже порога
    # Кто и когда последний раз вносил/менял отметку — для журнала группы
    # у администрации (см. обновление 1.1). У куратора в его собственном
    # кабинете эти поля есть, но не показываются.
    last_edited_by: str | None = None
    last_edited_at: datetime.datetime | None = None


class RosterResponse(BaseModel):
    study_group_id: int
    date: datetime.date
    is_submitted: bool
    submitted_at: datetime.datetime | None
    is_on_time: bool | None
    first_period: int | None = None
    entries: list[RosterEntry]
    # Кто сдал день — для итогов сданного дня.
    submitted_by_name: str | None = None
    # Правка этого дня текущим пользователем пойдёт на проверку зав. отделением.
    edit_requires_review: bool = False
    # Запрос на изменение, который ждёт решения, и последнее решение по этому дню.
    pending_change: "AttendanceChangeRead | None" = None
    last_change: "AttendanceChangeRead | None" = None


class MarkExceptionInput(BaseModel):
    student_id: int
    mark_code: str
    comment: str | None = Field(default=None, max_length=500)
    # Лимит совпадает с колонкой AttendanceMark.basis_reference в БД — иначе
    # MySQL strict mode роняет запрос необработанным 500 (см. TODO.md 3).
    basis_reference: str | None = Field(default=None, max_length=255)


class SubmitDayRequest(BaseModel):
    exceptions: list[MarkExceptionInput] = []
    first_period: int | None = Field(default=None, ge=1, le=10)


class GroupSummary(BaseModel):
    id: int
    code: str
    course: int
    is_submitted_today: bool
    # Для карточек «Мои группы»: сколько студентов сейчас и сколько в группе риска; кем ведёт.
    students_count: int = 0
    risk_count: int = 0
    role_type: str | None = None


class MonthDayStatus(BaseModel):
    date: datetime.date
    day_type: str
    is_submitted: bool | None
    is_on_time: bool | None
    # Сколько отметок уже стоит на этот день (для будущих дней — заранее внесённые).
    marks_count: int = 0


class AbsencePeriodCreate(BaseModel):
    student_id: int
    mark_code: str
    date_from: datetime.date
    date_to: datetime.date
    basis_reference: str | None = Field(default=None, max_length=255)


class AbsencePeriodRead(BaseModel):
    id: int
    student_id: int
    mark_code: str
    date_from: datetime.date
    date_to: datetime.date
    basis_reference: str | None


class MarkChange(BaseModel):
    """Что меняется у студента: код было → станет (None — «присутствовал»)."""

    student_id: int
    full_name: str
    from_code: str | None
    to_code: str | None
    details_changed: bool = False  # тот же код, но другой комментарий или основание


class AttendanceChangeRead(BaseModel):
    id: int
    study_group_id: int
    group_code: str
    date: datetime.date
    requested_by_id: int
    requested_by_name: str
    created_at: datetime.datetime
    reason: str
    status: str
    reviewed_by_name: str | None
    reviewed_at: datetime.datetime | None
    review_comment: str | None
    first_period: int | None
    changes: list[MarkChange]


class ChangeRequestInput(BaseModel):
    exceptions: list[MarkExceptionInput]
    first_period: int | None = Field(default=None, ge=1, le=10)
    reason: str = Field(min_length=3, max_length=500)


class ReviewDecision(BaseModel):
    comment: str | None = Field(default=None, max_length=500)


RosterResponse.model_rebuild()
