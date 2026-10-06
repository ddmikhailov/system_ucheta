"""Запросы на исправление прошлых сданных дней: список для зав. отделением и решения."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles, scope_department_id
from app.core import policies
from app.core.roles import is_department_scoped
from app.db.session import get_db
from app.models import RoleCode, User
from app.schemas.curator import AttendanceChangeRead, ReviewDecision
from app.services import attendance_change_service as changes
from app.services import attendance_service

router = APIRouter(prefix="/attendance-changes", tags=["attendance-changes"])

require_reviewer = require_roles(RoleCode.ADMIN, RoleCode.TUTOR, RoleCode.DEPT_HEAD)


@router.get("", response_model=list[AttendanceChangeRead])
def pending_changes(user: User = Depends(require_reviewer), db: Session = Depends(get_db)):
    """Ждущие решения запросы: зав. отделением и тьютору — своего отделения, администратору — все."""
    department_id = scope_department_id(user, None) if is_department_scoped(user) else None
    return [changes.to_read(db, r) for r in changes.list_pending(db, department_id)]


def _request_or_404(db: Session, request_id: int):
    req = changes.get(db, request_id)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Запрос не найден")
    return req


@router.post("/{request_id}/approve", response_model=AttendanceChangeRead)
def approve(request_id: int, payload: ReviewDecision, user: User = Depends(require_reviewer), db: Session = Depends(get_db)):
    req = _request_or_404(db, request_id)
    policies.assert_can_review_attendance_change(user, req.study_group)
    try:
        changes.approve(db, req, user, payload.comment)
    except changes.ChangeNotAllowed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except (attendance_service.BackdateNotAllowed, attendance_service.InvalidSubmission) as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Применить исправление нельзя: {exc}")
    return changes.to_read(db, _request_or_404(db, request_id), with_changes=False)


@router.post("/{request_id}/reject", response_model=AttendanceChangeRead)
def reject(request_id: int, payload: ReviewDecision, user: User = Depends(require_reviewer), db: Session = Depends(get_db)):
    req = _request_or_404(db, request_id)
    policies.assert_can_review_attendance_change(user, req.study_group)
    try:
        changes.reject(db, req, user, payload.comment)
    except changes.ChangeNotAllowed as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return changes.to_read(db, _request_or_404(db, request_id), with_changes=False)


@router.post("/{request_id}/cancel", response_model=AttendanceChangeRead)
def cancel(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Автор отзывает свой запрос, пока его не решили."""
    req = _request_or_404(db, request_id)
    try:
        changes.cancel(db, req, user)
    except changes.ChangeNotAllowed as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    return changes.to_read(db, _request_or_404(db, request_id), with_changes=False)
