from pydantic import BaseModel


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
    department_name: str | None = None
    groups: list[MeGroupInfo] = []
    dept_head_name: str | None = None
    telegram_linked: bool = False


class AcceptInvitationRequest(BaseModel):
    password: str


class InvitationPreview(BaseModel):
    full_name: str
    role: str
    groups: list[str] = []


class TelegramLinkResponse(BaseModel):
    deep_link: str
    expires_at: str
