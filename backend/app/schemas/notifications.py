import datetime

from pydantic import BaseModel


class NotificationRead(BaseModel):
    id: int
    kind: str
    message: str
    entity_type: str | None
    entity_id: str | None
    created_at: datetime.datetime
    read_at: datetime.datetime | None
    category: str = "work"


class UnreadCountResponse(BaseModel):
    unread: int  # всего
    unread_work: int = 0
    unread_manage: int = 0
