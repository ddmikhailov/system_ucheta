"""Запросы куратора на полное удаление студента: создание, список для руководителей и решения."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import assert_can_access_group, get_current_user, require_roles, scope_department_id
from app.core import policies
from app.core.time import today_local
from app.db.session import get_db
from app.models import RoleCode, Student, StudyGroup, User
from app.schemas.admin import DeleteResult
from app.schemas.curator import ReviewDecision
from app.schemas.students import StudentDeletionCreate, StudentDeletionRead
from app.services import student_deletion_service as deletions

router = APIRouter(prefix="/student-deletions", tags=["student-deletions"])

require_reviewer = require_roles(RoleCode.ADMIN, RoleCode.TUTOR, RoleCode.DEPT_HEAD)


def _read(db: Session, req) -> StudentDeletionRead:
    return deletions.to_read(req, db.get(StudyGroup, req.student.study_group_id).code)


def _request_or_404(db: Session, request_id: int):
    req = deletions.get(db, request_id)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Запрос не найден")
    return req


@router.get("", response_model=list[StudentDeletionRead])
def pending(user: User = Depends(require_reviewer), db: Session = Depends(get_db)):
    """Ждущие решения запросы: зав. отделением и тьютору — своего отделения, администратору — все."""
    department_id = scope_department_id(user, None)
    return [_read(db, r) for r in deletions.list_pending(db, department_id)]


@router.get("/for-student/{student_id}", response_model=StudentDeletionRead | None)
def for_student(student_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Последний запрос по студенту — для карточки (кнопка меняется на «запрос отправлен»)."""
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Студент не найден")
    assert_can_access_group(db, user, student.study_group_id, today_local())
    req = deletions.latest_for_student(db, student_id)
    return _read(db, req) if req else None


@router.post("", response_model=StudentDeletionRead, status_code=status.HTTP_201_CREATED)
def create(payload: StudentDeletionCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    student = db.get(Student, payload.student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Студент не найден")
    assert_can_access_group(db, user, student.study_group_id, today_local())
    try:
        req = deletions.create(db, user, student, payload.reason)
    except deletions.DeletionNotAllowed as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return _read(db, _request_or_404(db, req.id))


@router.post("/{request_id}/approve", response_model=DeleteResult)
def approve(request_id: int, user: User = Depends(require_reviewer), db: Session = Depends(get_db)):
    req = _request_or_404(db, request_id)
    policies.assert_can_review_student_deletion(user, db.get(StudyGroup, req.student.study_group_id))
    try:
        detail = deletions.approve(db, req, user)
    except deletions.DeletionNotAllowed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return DeleteResult(deleted=True, anonymized=False, detail=detail)


@router.post("/{request_id}/reject", response_model=StudentDeletionRead)
def reject(request_id: int, payload: ReviewDecision, user: User = Depends(require_reviewer), db: Session = Depends(get_db)):
    req = _request_or_404(db, request_id)
    policies.assert_can_review_student_deletion(user, db.get(StudyGroup, req.student.study_group_id))
    try:
        deletions.reject(db, req, user, payload.comment)
    except deletions.DeletionNotAllowed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return _read(db, _request_or_404(db, request_id))


@router.post("/{request_id}/cancel", response_model=StudentDeletionRead)
def cancel(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    req = _request_or_404(db, request_id)
    try:
        deletions.cancel(db, req, user)
    except deletions.DeletionNotAllowed as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    return _read(db, _request_or_404(db, request_id))
