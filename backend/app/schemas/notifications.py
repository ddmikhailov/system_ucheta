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


class UnreadCountResponse(BaseModel):
    unread: int
