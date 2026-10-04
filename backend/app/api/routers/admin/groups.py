"""Учебные группы: список, создание, правка, удаление (в том числе насовсем)."""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import (
    require_dept_editor,
    require_full_access,
    require_structure_editor,
    require_viewer,
    scope_department_id,
)
from app.core import policies
from app.core.roles import is_department_scoped
from app.core.time import today_local
from app.db.session import get_db
from app.models import (
    AbsencePeriod,
    AttendanceMark,
    CuratorAssignment,
    DaySubmission,
    GroupCalendarOverride,
    Student,
    StudentGroupMembership,
    StudyGroup,
    TaskAssignment,
    User,
)
from app.schemas.admin import (
    DeleteResult,
    GroupDeletionPreview,
    StudyGroupCreate,
    StudyGroupRead,
    StudyGroupUpdate,
)
from app.services import task_service
from app.services.erasure_service import erase_student_personal_data
from app.services.audit_service import log_action, redact_audit_history

router = APIRouter()


def _group_read(g: StudyGroup, today: datetime.date | None = None) -> StudyGroupRead:
    today = today or today_local()
    # Архивный куратор не должен продолжать числиться куратором группы (см.
    # TODO.md 3) — иначе группа не попадает в «Вакантные», хотя ей на самом
    # деле некому заниматься.
    curator_assignment = next(
        (
            a for a in g.curator_assignments
            if a.is_active_on(today) and a.role_type.value == "curator" and a.user.is_active
        ),
        None,
    )
    # Раньше замещающего вообще не было видно в админке (см. TODO.md 3) —
    # значит его нельзя было ни увидеть, ни снять, и он "навсегда" оставался
    # ответственным за группу в глазах интерфейса.
    deputy_assignment = next(
        (
            a for a in g.curator_assignments
            if a.is_active_on(today) and a.role_type.value == "deputy" and a.user.is_active
        ),
        None,
    )
    return StudyGroupRead(
        id=g.id, code=g.code, course=g.course, department_id=g.department_id,
        study_form=g.study_form, is_active=g.is_active,
        curator_name=curator_assignment.user.full_name if curator_assignment else None,
        curator_assignment_id=curator_assignment.id if curator_assignment else None,
        deputy_name=deputy_assignment.user.full_name if deputy_assignment else None,
        deputy_assignment_id=deputy_assignment.id if deputy_assignment else None,
    )




@router.get("/groups", response_model=list[StudyGroupRead])
def list_groups(
    department_id: int | None = None,
    user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    today = today_local()
    scope = scope_department_id(user, department_id)
    q = db.query(StudyGroup)
    if scope is not None:
        q = q.filter(StudyGroup.department_id == scope)
    groups = q.order_by(StudyGroup.course, StudyGroup.code).all()
    return [_group_read(g, today) for g in groups]


@router.post("/groups", response_model=StudyGroupRead, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: StudyGroupCreate, user: User = Depends(require_dept_editor), db: Session = Depends(get_db),
):
    if is_department_scoped(user) and payload.department_id != user.department_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Группу можно создать только в своём отделении")
    group = StudyGroup(**payload.model_dump())
    db.add(group)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Группа с таким кодом уже существует")
    db.refresh(group)
    log_action(db, user, "group.create", "study_group", str(group.id), new_value=group.code)
    task_service.assign_new_group(db, group)  # открытые задачи с подходящим охватом достаются и ей
    db.commit()
    return _group_read(group)


@router.patch("/groups/{group_id}", response_model=StudyGroupRead)
def update_group(
    group_id: int, payload: StudyGroupUpdate,
    user: User = Depends(require_structure_editor), db: Session = Depends(get_db),
):
    group = db.get(StudyGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    policies.assert_can_manage_group(user, group)

    data = payload.model_dump(exclude_unset=True)
    # Перенос группы в другое отделение — только администратор по колледжу.
    if "department_id" in data and is_department_scoped(user):
        data.pop("department_id")

    old_active = group.is_active
    for field, value in data.items():
        setattr(group, field, value)
    if group.is_active != old_active:
        if group.is_active:
            task_service.assign_new_group(db, group)
        log_action(
            db, user, "group.archive" if not group.is_active else "group.restore",
            "study_group", str(group.id),
        )
    else:
        log_action(db, user, "group.update", "study_group", str(group.id))

    db.commit()
    db.refresh(group)
    return _group_read(group)


def _group_student_ids(db: Session, group_id: int) -> list[int]:
    return [sid for (sid,) in db.query(Student.id).filter(Student.study_group_id == group_id).all()]


def _count_rows(db: Session, model, column, values: list[int]) -> int:
    if not values:
        return 0
    return db.query(model).filter(column.in_(values)).count()


@router.get("/groups/{group_id}/deletion-preview", response_model=GroupDeletionPreview)
def group_deletion_preview(
    group_id: int,
    user: User = Depends(require_full_access), db: Session = Depends(get_db),
):
    group = db.get(StudyGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    student_ids = _group_student_ids(db, group_id)
    return GroupDeletionPreview(
        code=group.code,
        students=len(student_ids),
        attendance_marks=_count_rows(db, AttendanceMark, AttendanceMark.student_id, student_ids),
        day_submissions=db.query(DaySubmission).filter(DaySubmission.study_group_id == group_id).count(),
        absence_periods=_count_rows(db, AbsencePeriod, AbsencePeriod.student_id, student_ids),
        curator_assignments=db.query(CuratorAssignment).filter(CuratorAssignment.study_group_id == group_id).count(),
    )


def _delete_group_completely(db: Session, user: User, group: StudyGroup) -> DeleteResult:
    """Удаление группы вместе со всем, что к ней относится: студенты, их
    отметки и длительные отсутствия, сдачи дней, назначения кураторов,
    исключения календаря. Необратимо — поэтому вызывается только явно
    (force + подтверждение кодом группы) и только администратором/тьютором.

    Студенты, которые раньше состояли в группе, но уже переведены в другую,
    не удаляются — у них убирается только запись о членстве в этой группе."""
    group_id = group.id
    code = group.code
    student_ids = _group_student_ids(db, group_id)

    counts = {
        "students": len(student_ids),
        "marks": _count_rows(db, AttendanceMark, AttendanceMark.student_id, student_ids),
        "submissions": db.query(DaySubmission).filter(DaySubmission.study_group_id == group_id).count(),
    }

    # Назначения задач группы вместе с ответами (каскадом) и личные данные её студентов.
    for assignment in db.query(TaskAssignment).filter(TaskAssignment.study_group_id == group_id).all():
        db.delete(assignment)
    db.flush()
    erase_student_personal_data(db, student_ids, include_access_log=True)

    if student_ids:
        db.query(AttendanceMark).filter(AttendanceMark.student_id.in_(student_ids)).delete(synchronize_session=False)
        db.query(AbsencePeriod).filter(AbsencePeriod.student_id.in_(student_ids)).delete(synchronize_session=False)
        db.query(StudentGroupMembership).filter(
            StudentGroupMembership.student_id.in_(student_ids)
        ).delete(synchronize_session=False)
        for student_id in student_ids:
            # ФИО осталось бы в audit_log (student.create хранит его в
            # new_value) — стираем, как при обезличивании студента.
            redact_audit_history(db, "student", str(student_id))
        db.query(Student).filter(Student.id.in_(student_ids)).delete(synchronize_session=False)

    db.query(StudentGroupMembership).filter(
        StudentGroupMembership.study_group_id == group_id
    ).delete(synchronize_session=False)
    db.query(DaySubmission).filter(DaySubmission.study_group_id == group_id).delete(synchronize_session=False)
    db.query(CuratorAssignment).filter(CuratorAssignment.study_group_id == group_id).delete(synchronize_session=False)
    db.query(GroupCalendarOverride).filter(
        GroupCalendarOverride.study_group_id == group_id
    ).delete(synchronize_session=False)
    db.expire_all()
    db.delete(db.get(StudyGroup, group_id))

    log_action(
        db, user, "group.delete_cascade", "study_group", str(group_id), old_value=code,
        new_value=f"students={counts['students']}, marks={counts['marks']}, submissions={counts['submissions']}",
    )
    db.commit()
    return DeleteResult(
        deleted=True, anonymized=False,
        detail=(
            f"Группа {code} удалена навсегда: студентов — {counts['students']}, "
            f"отметок — {counts['marks']}, сданных дней — {counts['submissions']}"
        ),
    )


@router.delete("/groups/{group_id}", response_model=DeleteResult)
def delete_group(
    group_id: int,
    force: bool = False,
    confirm_code: str | None = Query(default=None, max_length=32),
    user: User = Depends(require_structure_editor), db: Session = Depends(get_db),
):
    group = db.get(StudyGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    policies.assert_can_manage_group(user, group)
    if force:
        if user.role.code not in policies.ELEVATED_ROLES:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Полное удаление группы с историей доступно только администратору/тьютору"
            )
        if confirm_code != group.code:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Для полного удаления укажите код группы в confirm_code"
            )
        return _delete_group_completely(db, user, group)
    if group.is_active:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Сначала переведите группу в архив (снимите «активна») — удалить можно только из архива",
        )

    try:
        db.delete(group)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "У группы есть история (студенты, посещаемость, назначения кураторов) — "
            "удалить полностью нельзя, оставьте её в архиве",
        )

    log_action(db, user, "group.delete", "study_group", str(group_id))
    db.commit()
    return DeleteResult(deleted=True, anonymized=False, detail="Группа удалена")
