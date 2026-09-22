import datetime

from pydantic import BaseModel, Field


class DepartmentRead(BaseModel):
    id: int
    name: str
    is_active: bool


class DepartmentCreate(BaseModel):
    name: str


class StudyGroupRead(BaseModel):
    id: int
    code: str
    course: int
    department_id: int
    study_form: str | None
    is_active: bool
    curator_name: str | None = None


class StudyGroupCreate(BaseModel):
    code: str
    course: int
    department_id: int
    study_form: str | None = None


class StudentRead(BaseModel):
    id: int
    full_name: str
    study_group_id: int
    status: str
    enrolled_at: datetime.date
    left_at: datetime.date | None


class StudentCreate(BaseModel):
    last_name: str
    first_name: str
    middle_name: str | None = None
    study_group_id: int
    enrolled_at: datetime.date


class StudentUpdateStatus(BaseModel):
    status: str
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
    role_type: str
    start_date: datetime.date
    end_date: datetime.date | None = None


class UserCreate(BaseModel):
    full_name: str
    username: str
    role: str
    department_id: int | None = None


class UserRead(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
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
    """Редактирование логина/ФИО существующего пользователя администрацией."""

    username: str | None = None
    full_name: str | None = None
    department_id: int | None = None


class SetPasswordRequest(BaseModel):
    # Пусто — сгенерировать временный пароль самим, иначе — использовать
    # заданный администратором. В обоих случаях выставляется
    # must_change_password, чтобы человек задал свой пароль при входе.
    password: str | None = Field(default=None, min_length=8)


class SetPasswordResponse(BaseModel):
    username: str
    password: str


class InvitationRead(BaseModel):
    token: str
    expires_at: datetime.datetime
    invitation_url_path: str


class CalendarDayUpsert(BaseModel):
    date: datetime.date
    day_type: str
