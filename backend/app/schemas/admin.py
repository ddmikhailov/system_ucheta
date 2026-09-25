import datetime
from typing import Literal

from pydantic import BaseModel, Field

_DayTypeLiteral = Literal["study_day", "weekend", "holiday", "vacation", "remote"]


class DepartmentRead(BaseModel):
    id: int
    name: str
    is_active: bool


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None


class StudyGroupRead(BaseModel):
    id: int
    code: str
    course: int
    department_id: int
    study_form: str | None
    is_active: bool
    curator_name: str | None = None
    curator_assignment_id: int | None = None


class StudyGroupCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    course: int = Field(ge=1, le=6)
    department_id: int
    study_form: str | None = Field(default=None, max_length=64)


class StudyGroupUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=32)
    course: int | None = Field(default=None, ge=1, le=6)
    department_id: int | None = None
    study_form: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None


class DeleteResult(BaseModel):
    deleted: bool
    anonymized: bool
    detail: str


_StudentStatusLiteral = Literal["studying", "academic_leave", "expelled"]


class StudentRead(BaseModel):
    id: int
    full_name: str
    study_group_id: int
    status: str
    enrolled_at: datetime.date
    left_at: datetime.date | None


class StudentCreate(BaseModel):
    last_name: str = Field(min_length=1, max_length=128)
    first_name: str = Field(min_length=1, max_length=128)
    middle_name: str | None = Field(default=None, max_length=128)
    study_group_id: int
    enrolled_at: datetime.date


class StudentUpdateStatus(BaseModel):
    status: _StudentStatusLiteral
    left_at: datetime.date | None = None


class StudentUpdate(BaseModel):
    last_name: str | None = Field(default=None, min_length=1, max_length=128)
    first_name: str | None = Field(default=None, min_length=1, max_length=128)
    middle_name: str | None = Field(default=None, max_length=128)
    study_group_id: int | None = None
    status: _StudentStatusLiteral | None = None
    left_at: datetime.date | None = None


class MarkCodeRead(BaseModel):
    id: int
    code: str
    name: str
    counts_as_present: bool
    is_excused: bool
    requires_document: bool
    is_active: bool


class MarkCodeUpdate(BaseModel):
    counts_as_present: bool | None = None
    is_excused: bool | None = None
    requires_document: bool | None = None
    is_active: bool | None = None


class CuratorAssignmentCreate(BaseModel):
    study_group_id: int
    user_id: int
    role_type: Literal["curator", "deputy"]
    start_date: datetime.date
    end_date: datetime.date | None = None


class UserCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=64)
    role: str
    department_id: int | None = None
    display_title: str | None = Field(default=None, max_length=128)


class UserRead(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    display_title: str | None
    department_id: int | None
    is_active: bool
    telegram_linked: bool
    has_password: bool
    must_change_password: bool
    is_locked: bool
    receives_leadership_digest: bool


class UserUpdateLeadershipDigest(BaseModel):
    receives_leadership_digest: bool


class UserUpdate(BaseModel):
    """Редактирование логина/ФИО/статуса существующего пользователя администрацией."""

    username: str | None = Field(default=None, min_length=1, max_length=64)
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: str | None = None
    department_id: int | None = None
    is_active: bool | None = None
    display_title: str | None = Field(default=None, max_length=128)


class SetPasswordRequest(BaseModel):
    # Пусто — сгенерировать временный пароль самим, иначе — использовать
    # заданный администратором. В обоих случаях выставляется
    # must_change_password, чтобы человек задал свой пароль при входе.
    password: str | None = Field(default=None, min_length=8)


class SetPasswordResponse(BaseModel):
    username: str
    password: str


class CalendarDayUpsert(BaseModel):
    date: datetime.date
    day_type: _DayTypeLiteral


class GroupCalendarOverrideRead(BaseModel):
    study_group_id: int
    date: datetime.date
    day_type: str


class GroupCalendarOverrideUpsert(BaseModel):
    study_group_id: int
    date: datetime.date
    day_type: _DayTypeLiteral
