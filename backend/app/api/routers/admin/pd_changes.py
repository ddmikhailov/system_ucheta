import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.time import today_local
from app.db.session import get_db
from app.models import RoleCode, User
from app.schemas.admin import PdChangeRead
from app.services import pd_change_service
from app.services.audit_service import log_action

router = APIRouter()


@router.get("/pd-changes", response_model=list[PdChangeRead])
def pd_changes(
    month: datetime.date | None = None,
    admin: User = Depends(require_roles(RoleCode.ADMIN)),
    db: Session = Depends(get_db),
):
    """Изменения ПДн студентов за месяц (любая дата месяца; по умолчанию текущий) — для сообщения в отдел кадров."""
    result = pd_change_service.list_changes(db, month or today_local())
    log_action(db, admin, "pd_changes.view", "student", "*")
    db.commit()
    return result
