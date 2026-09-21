import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_management
from app.core.config import get_settings
from app.core.time import utcnow
from app.db.session import get_db
from app.models import AttendanceMark, BasisStatus, RoleCode, Student, User
from app.schemas.dashboards import (
    ConfirmBasisRequest,
    CuratorDisciplineRow,
    DayOverviewRow,
    DynamicsPoint,
    PendingBasisRow,
    RiskStudentRow,
    StudentCard,
    StudentMarkHistoryEntry,
)
from app.services import stats_service
from app.services.audit_service import log_action

router = APIRouter(prefix="/dashboards", tags=["dashboards"])
settings = get_settings()


def _scope_department_id(user: User, requested: int | None) -> int | None:
    """Зав. отделением всегда ограничен своим отделением, остальные видят по запросу."""
    if RoleCode(user.role.code) == RoleCode.DEPT_HEAD:
        return user.department_id
    return requested


@router.get("/day", response_model=list[DayOverviewRow])
def day_overview(
    date: datetime.date,
    department_id: int | None = None,
    user: User = Depends(require_management),
    db: Session = Depends(get_db),
):
    scope = _scope_department_id(user, department_id)
    rows = stats_service.day_overview(db, date, scope)
    return [DayOverviewRow(**r) for r in rows]


@router.get("/dynamics", response_model=list[DynamicsPoint])
def dynamics(
    date_from: datetime.date,
    date_to: datetime.date,
    department_id: int | None = None,
    course: int | None = None,
    study_group_id: int | None = None,
    student_id: int | None = None,
    user: User = Depends(require_management),
    db: Session = Depends(get_db),
):
    scope = _scope_department_id(user, department_id)
    rows = stats_service.dynamics(db, date_from, date_to, scope, course, study_group_id, student_id)
    return [DynamicsPoint(**r) for r in rows]


@router.get("/risk-students", response_model=list[RiskStudentRow])
def risk_students(
    as_of_date: datetime.date,
    threshold: int | None = None,
    department_id: int | None = None,
    user: User = Depends(require_management),
    db: Session = Depends(get_db),
):
    scope = _scope_department_id(user, department_id)
    rows = stats_service.risk_students(
        db, as_of_date, threshold or settings.risk_threshold_consecutive_unexcused, scope
    )
    return [RiskStudentRow(**r) for r in rows]


@router.get("/curator-discipline", response_model=list[CuratorDisciplineRow])
def curator_discipline(
    date_from: datetime.date,
    date_to: datetime.date,
    department_id: int | None = None,
    user: User = Depends(require_management),
    db: Session = Depends(get_db),
):
    scope = _scope_department_id(user, department_id)
    rows = stats_service.curator_discipline(db, date_from, date_to, scope)
    return [CuratorDisciplineRow(**r) for r in rows]


@router.get("/students/{student_id}", response_model=StudentCard)
def student_card(
    student_id: int,
    date_from: datetime.date,
    date_to: datetime.date,
    user: User = Depends(require_management),
    db: Session = Depends(get_db),
):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Студент не найден")

    if RoleCode(user.role.code) == RoleCode.DEPT_HEAD and student.study_group.department_id != user.department_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Студент не из вашего отделения")

    marks = (
        db.query(AttendanceMark)
        .filter(AttendanceMark.student_id == student_id)
        .filter(AttendanceMark.date >= date_from, AttendanceMark.date <= date_to)
        .order_by(AttendanceMark.date)
        .all()
    )
    stats = stats_service.compute_period_stats(db, date_from, date_to, student_id=student_id)

    return StudentCard(
        student_id=student.id,
        full_name=student.full_name,
        group_code=student.study_group.code,
        status=student.status,
        percent_period=stats.percent,
        history=[
            StudentMarkHistoryEntry(
                date=m.date,
                mark_code=m.mark_code.code,
                mark_name=m.mark_code.name,
                basis_reference=m.basis_reference,
                basis_status=m.basis_status,
            )
            for m in marks
        ],
    )


@router.get("/pending-basis", response_model=list[PendingBasisRow])
def pending_basis(
    department_id: int | None = None,
    user: User = Depends(require_management),
    db: Session = Depends(get_db),
):
    scope = _scope_department_id(user, department_id)
    today = datetime.date.today()

    q = (
        db.query(AttendanceMark)
        .join(Student, Student.id == AttendanceMark.student_id)
        .filter(AttendanceMark.basis_status == BasisStatus.PENDING)
    )
    if scope is not None:
        q = q.join(Student.study_group).filter_by(department_id=scope)

    rows = []
    for mark in q.all():
        rows.append(
            PendingBasisRow(
                mark_id=mark.id,
                student_id=mark.student_id,
                full_name=mark.student.full_name,
                group_code=mark.student.study_group.code,
                date=mark.date,
                mark_code=mark.mark_code.code,
                mark_name=mark.mark_code.name,
                basis_deadline=mark.basis_deadline,
                is_overdue=bool(mark.basis_deadline and mark.basis_deadline < today),
            )
        )
    return rows


@router.patch("/pending-basis/{mark_id}")
def confirm_basis(
    mark_id: int,
    payload: ConfirmBasisRequest,
    user: User = Depends(require_management),
    db: Session = Depends(get_db),
):
    mark = db.get(AttendanceMark, mark_id)
    if mark is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отметка не найдена")

    if RoleCode(user.role.code) == RoleCode.DEPT_HEAD:
        if mark.student.study_group.department_id != user.department_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Студент не из вашего отделения")

    old_reference = mark.basis_reference
    mark.basis_reference = payload.basis_reference
    mark.basis_status = BasisStatus.CONFIRMED
    mark.updated_by_user_id = user.id
    mark.updated_at = utcnow()
    log_action(
        db, user, "basis.confirm", "attendance_mark", str(mark.id),
        old_value=old_reference, new_value=payload.basis_reference,
    )
    db.commit()
    return {"mark_id": mark.id, "basis_reference": mark.basis_reference, "basis_status": mark.basis_status}
