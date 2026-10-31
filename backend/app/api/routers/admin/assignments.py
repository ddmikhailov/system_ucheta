"""Назначения кураторов на группы."""
import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_management
from app.core import policies
from app.core.time import today_local
from app.db.session import get_db
from app.models import AssignmentRole, CuratorAssignment, StudyGroup, User
from app.schemas.admin import CuratorAssignmentCreate
from app.services.audit_service import log_action
from app.services.in_app_notification_service import notify

router = APIRouter()


def _period(start: datetime.date, end: datetime.date | None) -> str:
    text = f"с {start:%d.%m.%Y}"
    return f"{text} по {end:%d.%m.%Y}" if end is not None else text


def _curator_overlapping(
    db: Session, group_id: int, start: datetime.date, end: datetime.date | None,
) -> list[CuratorAssignment]:
    """Основные кураторы группы, чей период пересекается с [start, end]."""
    rows = (
        db.query(CuratorAssignment)
        .filter(CuratorAssignment.study_group_id == group_id, CuratorAssignment.role_type == AssignmentRole.CURATOR)
        .filter((CuratorAssignment.end_date.is_(None)) | (CuratorAssignment.end_date >= start))
        .all()
    )
    return [a for a in rows if end is None or a.start_date <= end]


def _notify_substitution(
    db: Session, group: StudyGroup, deputy: User, start: datetime.date, end: datetime.date | None,
) -> None:
    """Уведомить обоих: заместителя — что ему передали группу, основного куратора — кто его заменит."""
    period = _period(start, end)
    notify(
        db, deputy, "curator_substitution",
        f"Вы замещаете куратора группы «{group.code}» {period}",
        "study_group", str(group.id),
    )
    for a in _curator_overlapping(db, group.id, start, end):
        if a.user.is_active and a.user_id != deputy.id:
            notify(
                db, a.user, "curator_substitution",
                f"Группу «{group.code}» {period} замещает {deputy.full_name}",
                "study_group", str(group.id),
            )


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

    scope = policies.scope_of(user)
    if not scope.within(group.department_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Группа не относится к вашему отделению")
    if not scope.within(curator.department_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Куратор не из вашего отделения")

    role_type = AssignmentRole(payload.role_type)
    same_role = (
        db.query(CuratorAssignment)
        .filter(
            CuratorAssignment.study_group_id == payload.study_group_id,
            CuratorAssignment.role_type == role_type,
        )
        .filter((CuratorAssignment.end_date.is_(None)) | (CuratorAssignment.end_date >= payload.start_date))
        .all()
    )
    to_close = same_role
    if role_type == AssignmentRole.DEPUTY:
        to_close = []
        # Заместитель — это замена куратора на даты: его период может быть в будущем и ограниченным.
        # Поэтому новый период не обрезает чужой, а упирается в него: пересечение запрещаем.
        # Исключение — прежнее поведение «сменить заместителя»: открытый период с даты начала
        # заканчивает предыдущего накануне.
        for prev in same_role:
            if payload.end_date is not None and prev.start_date > payload.end_date:
                continue
            if payload.end_date is None and prev.start_date < payload.start_date:
                to_close.append(prev)
                continue
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"В эти даты у группы уже есть заместитель: {prev.user.full_name} "
                f"({_period(prev.start_date, prev.end_date)}). Сначала снимите его или выберите другие даты",
            )
        main = _curator_overlapping(db, payload.study_group_id, payload.start_date, payload.end_date)
        if any(a.user_id == payload.user_id for a in main):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Этот сотрудник и так ведёт группу в эти даты")
    # Новое назначение на ту же роль (куратор/заместитель) в этой группе
    # автоматически завершает предыдущее активное — иначе на группе
    # оказывается два "текущих" куратора одновременно (см. TODO.md 3).
    for prev in to_close:
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
    if role_type == AssignmentRole.DEPUTY:
        _notify_substitution(db, group, curator, payload.start_date, payload.end_date)
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
    if assignment.start_date > today:
        # Заместитель ещё не приступал — это отмена, в истории ей места нет.
        log_action(db, user, "curator_assignment.cancel", "curator_assignment", str(assignment.id))
        db.delete(assignment)
        db.commit()
        return {"id": assignment_id, "end_date": None}
    if assignment.end_date is None or assignment.end_date > today:
        assignment.end_date = today
    log_action(db, user, "curator_assignment.end", "curator_assignment", str(assignment.id))
    db.commit()
    return {"id": assignment.id, "end_date": assignment.end_date}
