from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import assert_can_access_group, get_current_user
from app.core.policies import scope_of
from app.core.time import today_local
from app.db.session import get_db
from app.models import RoleCode, StudyGroup, User
from app.schemas.subjects import SubjectRead, SubjectsRead, SubjectWrite
from app.services import subject_service

router = APIRouter(prefix="/groups/{group_id}/subjects", tags=["subjects"])


def _read_access(db: Session, user: User, group_id: int) -> None:
    """Читает тот, кто видит группу: куратор и заместитель — свою, отделение — своё, соц. педагог, психолог, админ — любую."""
    if db.get(StudyGroup, group_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    if RoleCode(user.role.code) == RoleCode.MEAL_MANAGER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа")
    scope_of(user, "view").require_group(db, group_id, today_local())


def _write_access(db: Session, user: User, group_id: int) -> None:
    _read_access(db, user, group_id)
    assert_can_access_group(db, user, group_id, today_local())


@router.get("", response_model=SubjectsRead)
def list_subjects(group_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _read_access(db, user, group_id)
    try:
        _write_access(db, user, group_id)
        can_edit = True
    except HTTPException:
        can_edit = False
    return SubjectsRead(can_edit=can_edit, subjects=subject_service.list_subjects(db, group_id))


@router.post("", response_model=SubjectRead, status_code=status.HTTP_201_CREATED)
def create_subject(group_id: int, payload: SubjectWrite, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _write_access(db, user, group_id)
    return subject_service.create_subject(db, group_id, payload, user)


@router.put("/{subject_id}", response_model=SubjectRead)
def update_subject(group_id: int, subject_id: int, payload: SubjectWrite, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _write_access(db, user, group_id)
    return subject_service.update_subject(db, group_id, subject_id, payload, user)


@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(group_id: int, subject_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _write_access(db, user, group_id)
    subject_service.delete_subject(db, group_id, subject_id)
