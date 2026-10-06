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
    deputy_name: str | None = None
    deputy_assignment_id: int | None = None


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


class GroupDeletionPreview(BaseModel):
    """Что будет безвозвратно удалено вместе с группой — показывается в
    окне подтверждения до самого удаления."""

    code: str
    students: int
    attendance_marks: int
    day_submissions: int
    absence_periods: int
    curator_assignments: int


_StudentStatusLiteral = Literal["studying", "academic_leave", "expelled"]


class StudentRead(BaseModel):
    id: int
    full_name: str
    last_name: str
    first_name: str
    middle_name: str | None
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
    has_password: bool
    must_change_password: bool
    is_locked: bool


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


class UserGroupLink(BaseModel):
    """Закрепление пользователя за группой (куратор или заместитель), с историей."""

    group_id: int
    group_code: str
    course: int
    department_name: str | None
    role_type: Literal["curator", "deputy"]
    start_date: datetime.date
    end_date: datetime.date | None
    is_current: bool
    students_count: int


class UserDiscipline(BaseModel):
    """Сдача дней по группам, которые человек ведёт сейчас, за последние 30 дней (без сегодня)."""

    date_from: datetime.date
    date_to: datetime.date
    study_days: int
    submitted: int
    on_time: int
    late: int
    missed: int
    percent_on_time: int | None


class UserTaskStats(BaseModel):
    """Задачи администрации по группам человека (срок — не раньше 90 дней назад)."""

    total: int
    accepted: int
    submitted: int
    in_work: int
    returned: int
    overdue: int


class UserActivityDay(BaseModel):
    date: datetime.date
    count: int


class UserProfile(BaseModel):
    user: UserRead
    department_name: str | None
    created_at: datetime.datetime
    last_activity_at: datetime.datetime | None
    groups: list[UserGroupLink]
    discipline: UserDiscipline
    tasks: UserTaskStats
    marks_created_30d: int
    days_submitted_30d: int
    notes_written_30d: int
    follow_ups_open: int
    dossier_views_30d: int
    activity_30d: list[UserActivityDay]


class UserActivityEntry(BaseModel):
    """Строка журнала действий: что сделано и когда. Значения «было/стало» не отдаются —
    в них бывают ФИО и данные досье, а для обзора работы человека достаточно факта."""

    id: int
    action: str
    entity_type: str
    entity_id: str
    created_at: datetime.datetime


class UserActivityPage(BaseModel):
    items: list[UserActivityEntry]
    next_before_id: int | None
