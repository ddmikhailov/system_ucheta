"""Журнал индивидуальной работы: обзор по группе (кто в группе внимания, с кем что делалось)."""
import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.time import today_local
from app.db.session import get_db
from app.models import User
from app.services import individual_work_service as svc
from app.services import passport_service

router = APIRouter(prefix="/individual-work", tags=["individual-work"])


class GroupOption(BaseModel):
    id: int
    code: str
    course: int


class WorkRowRead(BaseModel):
    student_id: int
    full_name: str
    risk_streak: int
    is_risk: bool
    work_count: int
    last_work_on: datetime.date | None
    next_follow_up_on: datetime.date | None
    follow_up_overdue: bool
    needs_attention: bool


class GroupWorkRead(BaseModel):
    group_id: int
    group_code: str
    no_work_days: int
    rows: list[WorkRowRead]


@router.get("/groups", response_model=list[GroupOption])
def groups(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Группы, в которых пользователь вправе смотреть журнал (те же, что у соц. паспорта)."""
    return [GroupOption(id=g.id, code=g.code, course=g.course) for g in passport_service.accessible_groups(db, user)]


@router.get("/groups/{group_id}", response_model=GroupWorkRead)
def group_work(group_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    allowed = {g.id: g for g in passport_service.accessible_groups(db, user)}
    group = allowed.get(group_id)
    if group is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этой группе")
    rows = svc.group_overview(db, group_id, today_local())
    return GroupWorkRead(
        group_id=group.id, group_code=group.code, no_work_days=svc.NO_WORK_DAYS,
        rows=[WorkRowRead(**vars(r)) for r in rows],
    )
