import datetime

from pydantic import BaseModel


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
    comment: str | None = None
    basis_reference: str | None = None


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
    basis_reference: str | None = None


class AbsencePeriodRead(BaseModel):
    id: int
    student_id: int
    mark_code: str
    date_from: datetime.date
    date_to: datetime.date
    basis_reference: str | None
