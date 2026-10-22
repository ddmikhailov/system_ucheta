"""Вкладка «Отладка» в админке: полный журнал действий всех пользователей — чтобы разобрать, кто что сделал
и что привело к результату. Читается только по запросу администратора; записи старше срока хранения
удаляет audit_service.purge_expired."""
import datetime

from sqlalchemy.orm import Session, joinedload

from app.core.time import local_to_utc
from app.models import AuditLog, User
from app.schemas.debug import AuditEntry, AuditPage

PAGE_MAX = 200


def audit_page(
    db: Session,
    *,
    before_id: int | None = None,
    limit: int = 100,
    user_id: int | None = None,
    area: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
) -> AuditPage:
    """Новые сверху, листается по id. Даты — по времени колледжа, обе границы включительно;
    `area` — начало кода действия («mark», «day», «task»…)."""
    limit = min(max(limit, 1), PAGE_MAX)
    query = db.query(AuditLog).options(joinedload(AuditLog.user).joinedload(User.role))
    if before_id is not None:
        query = query.filter(AuditLog.id < before_id)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if area:
        query = query.filter(AuditLog.action.like(f"{area}.%"))
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if date_from:
        query = query.filter(AuditLog.created_at >= local_to_utc(datetime.datetime.combine(date_from, datetime.time())))
    if date_to:
        next_day = datetime.datetime.combine(date_to + datetime.timedelta(days=1), datetime.time())
        query = query.filter(AuditLog.created_at < local_to_utc(next_day))
    rows = query.order_by(AuditLog.id.desc()).limit(limit + 1).all()
    items = [
        AuditEntry(
            id=r.id, created_at=r.created_at, user_id=r.user_id,
            user_name=r.user.full_name if r.user else None,
            user_role=r.user.role.code if r.user else None,
            action=r.action, entity_type=r.entity_type, entity_id=r.entity_id,
            old_value=r.old_value, new_value=r.new_value, ip_address=r.ip_address,
        )
        for r in rows[:limit]
    ]
    return AuditPage(items=items, next_before_id=items[-1].id if len(rows) > limit else None)
