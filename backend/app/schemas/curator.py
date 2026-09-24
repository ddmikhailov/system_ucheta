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
    risk_streak: int
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
    entries: list[RosterEntry]


class MarkExceptionInput(BaseModel):
    student_id: int
    mark_code: str
    comment: str | None = Field(default=None, max_length=500)
    # Лимит совпадает с колонкой AttendanceMark.basis_reference в БД — иначе
    # MySQL strict mode роняет запрос необработанным 500 (см. TODO.md 3).
    basis_reference: str | None = Field(default=None, max_length=255)


class SubmitDayRequest(BaseModel):
    exceptions: list[MarkExceptionInput] = []


class GroupSummary(BaseModel):
    id: int
    code: str
    course: int
    is_submitted_today: bool


class MonthDayStatus(BaseModel):
    date: datetime.date
    day_type: str
    is_submitted: bool | None
    is_on_time: bool | None


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
