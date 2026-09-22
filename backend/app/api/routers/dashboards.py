import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_management
from app.core.config import get_settings
from app.db.session import get_db
from app.models import AttendanceMark, RoleCode, Student, User
from app.schemas.dashboards import (
    CuratorDisciplineRow,
    DayOverviewRow,
    DynamicsPoint,
    RiskStudentRow,
    StudentCard,
    StudentMarkHistoryEntry,
)
from app.services import stats_service

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




