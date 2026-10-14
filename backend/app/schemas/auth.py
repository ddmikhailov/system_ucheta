from pydantic import BaseModel, Field

from app.core.password_policy import MAX_PASSWORD_LENGTH


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeGroupInfo(BaseModel):
    id: int
    code: str
    course: int


class MeResponse(BaseModel):
    id: int
    full_name: str
    role: str
    display_title: str | None = None
    department_name: str | None = None
    groups: list[MeGroupInfo] = []
    dept_head_name: str | None = None
    must_change_password: bool = False
    # Заполняется только ответом /auth/change-password (см. TODO.md 2 —
    # смена пароля отзывает все ранее выданные токены, включая тот, которым
    # выполнен сам этот запрос, поэтому новый нужно вернуть тут же).
    access_token: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str | None = None
    # Длина и сложность — в validate_password_strength (понятные сообщения вместо 422).
    new_password: str = Field(max_length=MAX_PASSWORD_LENGTH)

