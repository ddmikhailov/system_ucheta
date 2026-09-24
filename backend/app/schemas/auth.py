from pydantic import BaseModel, Field


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
    telegram_linked: bool = False
    must_change_password: bool = False
    # Заполняется только ответом /auth/change-password (см. TODO.md 2 —
    # смена пароля отзывает все ранее выданные токены, включая тот, которым
    # выполнен сам этот запрос, поэтому новый нужно вернуть тут же).
    access_token: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str | None = None
    new_password: str = Field(min_length=8)


class TelegramLinkResponse(BaseModel):
    deep_link: str
    expires_at: str
