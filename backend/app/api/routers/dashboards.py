import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import is_department_scoped, require_management, require_roles, require_viewer, scope_department_id, validate_date_range
from app.core import policies
from app.core.config import get_settings
from app.db.session import get_db
from app.models import AttendanceMark, RoleCode, Student, StudyGroup, User
from app.schemas.dashboards import (
    CuratorDaysRead,
    CuratorDisciplineRow,
    DayOverviewRow,
    DynamicsPoint,
    RiskStudentRow,
    StudentCard,
    StudentMarkHistoryEntry,
    SummaryCode,
    SummaryGroupDayRead,
    SummaryLineRead,
    SummaryRead,
)
from app.services import stats_service, summary_service

router = APIRouter(prefix="/dashboards", tags=["dashboards"])
settings = get_settings()


@router.get("/day", response_model=list[DayOverviewRow])
def day_overview(
    date: datetime.date,
    department_id: int | None = None,
    user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    scope = scope_department_id(user, department_id)
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
    user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    validate_date_range(date_from, date_to)
    scope = scope_department_id(user, department_id)
    rows = stats_service.dynamics(db, date_from, date_to, scope, course, study_group_id, student_id)
    return [DynamicsPoint(**r) for r in rows]


def _line_read(line: summary_service.SummaryLine) -> SummaryLineRead:
    t = line.totals
    return SummaryLineRead(
        date=line.date, department=line.department, slice_name=line.slice_name, groups=line.groups,
        groups_submitted=t.groups_submitted, headcount=t.headcount, counted=t.counted,
        present=t.present, absent=t.absent, percent=t.percent, by_code=t.by_code,
    )


@router.get("/summary", response_model=SummaryRead)
def summary(
    date_from: datetime.date,
    date_to: datetime.date,
    department_id: int | None = None,
    course: int | None = None,
    study_group_id: int | None = None,
    pair: int = Query(default=1, ge=1, le=10),
    include_group_days: bool = False,
    user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """Свод «всего / к 1 паре» — те же числа, что в листах свода в Excel.
    Разбивка по группам и дням тяжёлая на длинных периодах — отдаётся только
    по явному запросу (include_group_days)."""
    validate_date_range(date_from, date_to)
    scope = scope_department_id(user, department_id)
    result = summary_service.build_summary(db, date_from, date_to, scope, course, study_group_id, pair)
    group_days = []
    if include_group_days:
        for r in result.group_days:
            t = summary_service.totals_for([r])
            group_days.append(
                SummaryGroupDayRead(
                    date=r.date, department=r.department_name, group_id=r.group_id, group_code=r.group_code,
                    course=r.course, headcount=r.headcount, is_submitted=r.is_submitted,
                    present=r.present if r.is_submitted else None, absent=r.absent if r.is_submitted else None,
                    percent=t.percent, first_period=r.first_period, by_code=r.by_code,
                )
            )
    return SummaryRead(
        codes=[SummaryCode(code=c.code, name=c.name, counts_as_present=c.counts_as_present) for c in result.codes],
        daily=[_line_read(x) for x in result.daily],
        period=[_line_read(x) for x in result.period],
        group_days=group_days,
    )


@router.get("/risk-students", response_model=list[RiskStudentRow])
def risk_students(
    as_of_date: datetime.date,
    threshold: int | None = None,
    department_id: int | None = None,
    user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    scope = scope_department_id(user, department_id)
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
    validate_date_range(date_from, date_to)
    scope = scope_department_id(user, department_id)
    rows = stats_service.curator_discipline(db, date_from, date_to, scope)
    return [CuratorDisciplineRow(**r) for r in rows]


@router.get("/curator-discipline/{study_group_id}/days", response_model=CuratorDaysRead)
def curator_discipline_days(
    study_group_id: int,
    date_from: datetime.date,
    date_to: datetime.date,
    user: User = Depends(require_roles(RoleCode.DEPT_HEAD, RoleCode.TUTOR)),
    db: Session = Depends(get_db),
):
    """Во сколько куратор группы сдавал каждый день — только зав. отделением
    и только по группам своего отделения."""
    validate_date_range(date_from, date_to)
    group = db.get(StudyGroup, study_group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Группа не найдена")
    policies.assert_can_manage_group(user, group)
    return CuratorDaysRead(**stats_service.curator_discipline_days(db, group, date_from, date_to))


@router.get("/students/{student_id}", response_model=StudentCard)
def student_card(
    student_id: int,
    date_from: datetime.date,
    date_to: datetime.date,
    user: User = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    validate_date_range(date_from, date_to)
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Студент не найден")

    if is_department_scoped(user) and student.study_group.department_id != user.department_id:
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




