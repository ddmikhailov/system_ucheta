import datetime
from typing import Literal

from pydantic import BaseModel, Field

NoteKind = Literal["conversation", "call", "parent_invited", "prevention_council", "home_visit", "incident", "agreement", "other"]


class ProfileFields(BaseModel):
    birth_date: datetime.date | None = None
    gender: Literal["male", "female"] | None = None
    funding: Literal["budget", "contract"] | None = None
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    messenger: str | None = Field(default=None, max_length=128)
    registration_address: str | None = Field(default=None, max_length=512)
    residence_address: str | None = Field(default=None, max_length=512)
    additional_education: str | None = Field(default=None, max_length=1000)


class SpecialData(BaseModel):
    """Особые категории ПДн — хранятся в БД только в зашифрованном виде."""

    is_orphan: bool = False
    under_guardianship: bool = False
    disability_group: str | None = Field(default=None, max_length=32)
    has_ovz: bool = False
    large_family: bool = False
    low_income: bool = False
    pdn_kdn: bool = False
    internal_record: bool = False
    scholarship: str | None = Field(default=None, max_length=128)
    health_note: str | None = Field(default=None, max_length=2000)


class ProfileUpdate(ProfileFields):
    # None — особые поля не трогаем (их может не быть в форме / нет ключа).
    special: SpecialData | None = None


class GuardianIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    relation: str = Field(min_length=1, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    is_primary: bool = False


class GuardianRead(GuardianIn):
    id: int


class NoteIn(BaseModel):
    kind: NoteKind = "other"
    text: str = Field(min_length=1, max_length=5000)
    occurred_on: datetime.date | None = None  # когда это было; по умолчанию — сегодня
    follow_up_on: datetime.date | None = None  # когда вернуться к вопросу


class FollowUpIn(BaseModel):
    done: bool


class NoteRead(BaseModel):
    id: int
    kind: str
    text: str
    author_id: int | None
    author_name: str | None
    created_at: datetime.datetime
    can_delete: bool
    occurred_on: datetime.date | None = None
    follow_up_on: datetime.date | None = None
    follow_up_done: bool = False


class DossierRead(BaseModel):
    student_id: int
    profile: ProfileFields
    special: SpecialData | None
    # False — ключ шифрования не настроен: особые поля недоступны.
    special_available: bool
    guardians: list[GuardianRead]
    notes: list[NoteRead]


class AccessLogRead(BaseModel):
    user_id: int
    user_name: str
    included_special: bool
    created_at: datetime.datetime
