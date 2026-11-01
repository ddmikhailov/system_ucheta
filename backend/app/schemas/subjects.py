import datetime

from pydantic import BaseModel, Field, field_validator


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


class SubjectWrite(BaseModel):
    code: str | None = Field(default=None, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    teacher_name: str | None = Field(default=None, max_length=255)
    teacher_phone: str | None = Field(default=None, max_length=32)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("code", "name", "teacher_name", "teacher_phone", "note")
    @classmethod
    def strip_spaces(cls, value: str | None) -> str | None:
        return _clean(value)

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, value: str | None) -> str | None:
        if not value:
            raise ValueError("Укажите название дисциплины")
        return value


class SubjectRead(BaseModel):
    id: int
    study_group_id: int
    code: str | None
    name: str
    teacher_name: str | None
    teacher_phone: str | None
    note: str | None
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class SubjectsRead(BaseModel):
    can_edit: bool
    subjects: list[SubjectRead]
