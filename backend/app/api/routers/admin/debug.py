import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.session import get_db
from app.models import RoleCode, User
from app.schemas.debug import AuditPage
from app.services import debug_service
from app.services.audit_service import log_action

router = APIRouter()


@router.get("/debug/audit", response_model=AuditPage)
def debug_audit(
    before_id: int | None = None,
    limit: int = 100,
    user_id: int | None = None,
    area: str | None = Query(default=None, pattern=r"^[a-z_]{1,32}$"),
    entity_type: str | None = Query(default=None, max_length=64),
    entity_id: str | None = Query(default=None, max_length=64),
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    admin: User = Depends(require_roles(RoleCode.ADMIN)),
    db: Session = Depends(get_db),
):
    """Полный журнал действий (вкладка «Отладка»): только администратор и только по запросу — интерфейс
    обращается сюда лишь при открытии вкладки. В отличие от ленты в профиле, отдаёт и «было/стало»:
    без них не понять, что привело к результату. Сам просмотр (первая страница) пишется в журнал."""
    page = debug_service.audit_page(
        db, before_id=before_id, limit=limit, user_id=user_id, area=area,
        entity_type=entity_type, entity_id=entity_id, date_from=date_from, date_to=date_to,
    )
    if before_id is None:
        filters = {"user_id": user_id, "area": area, "entity_type": entity_type, "entity_id": entity_id,
                   "date_from": date_from, "date_to": date_to}
        log_action(db, admin, "debug.audit_view", "audit_log", "*",
                   new_value=", ".join(f"{k}={v}" for k, v in filters.items() if v is not None) or None)
        db.commit()
    return page
