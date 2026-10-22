from pydantic import BaseModel, Field


class ClientContext(BaseModel):
    """Что интерфейс прикладывает сам: человеку не нужно объяснять, где и в чём он работал."""

    page: str = Field(default="", max_length=300)
    version: str = Field(default="", max_length=16)
    browser: str = Field(default="", max_length=120)
    screen: str = Field(default="", max_length=20)


class ProblemReportRequest(ClientContext):
    text: str = Field(min_length=1, max_length=1000)


class ProblemReportResponse(BaseModel):
    # Скольким администраторам ушло уведомление (0 — ни одного активного администратора).
    delivered: int


class ClientErrorRequest(ClientContext):
    message: str = Field(min_length=1, max_length=500)
    stack: str = Field(default="", max_length=4000)


class ReleaseSeenRequest(BaseModel):
    release: str = Field(min_length=1, max_length=16)
