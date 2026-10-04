"""Назначения кураторов на группы."""
import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_management
from app.core import policies
from app.core.roles import is_department_scoped
from app.core.time import today_local
from app.db.session import get_db
from app.models import AssignmentRole, CuratorAssignment, StudyGroup, User
from app.schemas.admin import CuratorAssignmentCreate
from app.services.audit_service import log_action

router = APIRouter()


@router.post("/curator-assignments", status_code=status.HTTP_201_CREATED)
def create_curator_assignment(
    payload: CuratorAssignmentCreate,
    user: User = Depends(require_management),
    db: Session = Depends(get_db),
):
    group = db.get(StudyGroup, payload.study_group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    curator = db.get(User, payload.user_id)
    if curator is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не найден")
    if not curator.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь в архиве — сначала восстановите его")
    if curator.role.code not in policies.CURATOR_CAPABLE_ROLES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Назначать на группу можно куратора, заместителя, соц. педагога или психолога",
        )
    if payload.end_date is not None and payload.end_date < payload.start_date:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Дата окончания раньше даты начала")

    if is_department_scoped(user):
        if group.department_id != user.department_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Группа не относится к вашему отделению")
        if curator.department_id != user.department_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Куратор не из вашего отделения")

    role_type = AssignmentRole(payload.role_type)
    # Новое назначение на ту же роль (куратор/заместитель) в этой группе
    # автоматически завершает предыдущее активное — иначе на группе
    # оказывается два "текущих" куратора одновременно (см. TODO.md 3).
    previous_active = (
        db.query(CuratorAssignment)
        .filter(
            CuratorAssignment.study_group_id == payload.study_group_id,
            CuratorAssignment.role_type == role_type,
        )
        .filter((CuratorAssignment.end_date.is_(None)) | (CuratorAssignment.end_date >= payload.start_date))
        .all()
    )
    for prev in previous_active:
        prev.end_date = payload.start_date - datetime.timedelta(days=1)

    assignment = CuratorAssignment(
        study_group_id=payload.study_group_id, user_id=payload.user_id,
        role_type=role_type, start_date=payload.start_date, end_date=payload.end_date,
    )
    db.add(assignment)
    log_action(
        db, user, "curator_assignment.create", "curator_assignment",
        f"{payload.study_group_id}:{payload.user_id}",
    )
    db.commit()
    db.refresh(assignment)
    return {"id": assignment.id}


@router.post("/curator-assignments/{assignment_id}/end")
def end_curator_assignment(
    assignment_id: int,
    user: User = Depends(require_management),
    db: Session = Depends(get_db),
):
    """Снять куратора/заместителя с группы — назначение не удаляется, а
    завершается датой, чтобы история «кто вёл группу когда» не терялась."""
    assignment = db.get(CuratorAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Назначение не найдено")
    policies.assert_can_manage_group(user, assignment.study_group)

    today = today_local()
    if assignment.end_date is None or assignment.end_date > today:
        assignment.end_date = today
    log_action(db, user, "curator_assignment.end", "curator_assignment", str(assignment.id))
    db.commit()
    return {"id": assignment.id, "end_date": assignment.end_date}
