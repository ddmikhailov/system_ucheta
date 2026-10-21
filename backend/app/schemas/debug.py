import datetime

from pydantic import BaseModel


class AuditEntry(BaseModel):
    """Строка полного журнала действий для вкладки «Отладка»: кто, когда, что, над чем и что было/стало."""

    id: int
    created_at: datetime.datetime
    user_id: int | None
    user_name: str | None
    user_role: str | None
    action: str
    entity_type: str
    entity_id: str
    old_value: str | None
    new_value: str | None
    ip_address: str | None


class AuditPage(BaseModel):
    items: list[AuditEntry]
    next_before_id: int | None
