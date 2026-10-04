import calendar
import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.api.deps import assert_can_access_group, get_current_user, scope_department_id
from app.core.roles import DOSSIER_STAFF_ROLES, is_department_scoped
from app.core.time import today_local
from app.db.session import get_db
from app.models import (
    AttendanceMark,
    DaySubmission,
    DayType,
    RoleCode,
    Student,
    StudentGroupMembership,
    StudyGroup,
    User,
)
from app.schemas.students import (
    StudentCard,
    StudentCardGroup,
    StudentCardMark,
    StudentCardMembership,
    StudentCardStats,
    StudentDayAttendance,
    StudentMonthAttendance,
    StudentMonthSummary,
)
from app.services import calendar_service, group_membership_service, stats_service

router = APIRouter(prefix="/students", tags=["students"])

_ATTENDABLE = (DayType.STUDY_DAY, DayType.REMOTE)


def _get_accessible_student(db: Session, user: User, student_id: int) -> Student:
    """Карточку видят все роли, но только по студентам, к группе которых у них
    есть доступ: куратор/заместитель — своих групп, зав. отделением — своего
    отделения, администрация — всех."""
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Студент не найден")
    if RoleCode(user.role.code) in DOSSIER_STAFF_ROLES:
        return student
    assert_can_access_group(db, user, student.study_group_id, today_local())
    return student


class StudentSearchRow(BaseModel):
    id: int
    full_name: str
    group_code: str
    status: str


@router.get("", response_model=list[StudentSearchRow])
def search_students(
    q: str = "", group_id: int | None = None, limit: int = 50,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Поиск студента по ФИО/группе — вход в карточку и досье для соц. педагога,
    психолога и администрации. Куратор работает через «Мои группы»."""
    role = RoleCode(user.role.code)
    if role in (RoleCode.CURATOR, RoleCode.DEPUTY_CURATOR):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
    query = db.query(Student).join(StudyGroup, StudyGroup.id == Student.study_group_id)
    if is_department_scoped(user):
        query = query.filter(StudyGroup.department_id == scope_department_id(user, None))
    if group_id is not None:
        query = query.filter(Student.study_group_id == group_id)
    for word in q.split():
        like = f"%{word}%"
        query = query.filter(
            Student.last_name.ilike(like) | Student.first_name.ilike(like)
            | Student.middle_name.ilike(like) | StudyGroup.code.ilike(like)
        )
    students = (
        query.options(joinedload(Student.study_group))
        .order_by(Student.last_name, Student.first_name).limit(min(max(limit, 1), 200)).all()
    )
    return [
        StudentSearchRow(id=s.id, full_name=s.full_name, group_code=s.study_group.code, status=s.status.value)
        for s in students
    ]


@router.get("/{student_id}", response_model=StudentCard)
def get_student_card(
    student_id: int,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    student = _get_accessible_student(db, user, student_id)

    today = today_local()
    group = student.study_group
    curator_name = deputy_name = None
    for a in group.curator_assignments:
        if not (a.is_active_on(today) and a.user.is_active):
            continue
        if a.role_type.value == "curator" and curator_name is None:
            curator_name = a.user.full_name
        elif a.role_type.value == "deputy" and deputy_name is None:
            deputy_name = a.user.full_name

    history = (
        db.query(StudentGroupMembership)
        .filter(StudentGroupMembership.student_id == student.id)
        .order_by(StudentGroupMembership.start_date)
        .all()
    )

    stats_from = today - datetime.timedelta(days=29)
    stats = stats_service.compute_period_stats(
        db, stats_from, today, student_id=student.id, only_submitted=True
    )
    marks = (
        db.query(AttendanceMark)
        .filter(AttendanceMark.student_id == student.id)
        .order_by(AttendanceMark.date.desc())
        .limit(20)
        .all()
    )

    return StudentCard(
        id=student.id, full_name=student.full_name,
        last_name=student.last_name, first_name=student.first_name, middle_name=student.middle_name,
        status=student.status.value, enrolled_at=student.enrolled_at, left_at=student.left_at,
        group=StudentCardGroup(
            id=group.id, code=group.code, course=group.course, study_form=group.study_form,
            is_active=group.is_active, department_id=group.department_id,
            department_name=group.department.name,
        ),
        curator_name=curator_name, deputy_name=deputy_name,
        group_history=[
            StudentCardMembership(
                group_id=m.study_group_id, group_code=m.study_group.code,
                start_date=m.start_date, end_date=m.end_date,
            )
            for m in history
        ],
        stats=StudentCardStats(
            date_from=stats_from, date_to=today, in_list=stats.in_list, present=stats.present,
            absent_total=stats.absent_total, absent_excused=stats.absent_excused,
            absent_unexcused=stats.absent_unexcused, late=stats.late, percent=stats.percent,
            by_code=stats.by_code,
        ),
        recent_marks=[
            StudentCardMark(
                date=m.date, code=m.mark_code.code, name=m.mark_code.name,
                comment=m.comment, basis_reference=m.basis_reference,
            )
            for m in marks
        ],
    )


@router.get("/{student_id}/attendance", response_model=StudentMonthAttendance)
def get_student_month_attendance(
    student_id: int,
    year: int,
    month: int,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Посещаемость студента по дням за месяц — для листания по месяцам на
    его карточке. Показывает каждый день до сегодняшнего: учебный или нет,
    присутствовал / какая отметка / группа не сдала день."""
    if not (1 <= month <= 12) or not (2000 <= year <= 2100):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Некорректные год/месяц")
    student = _get_accessible_student(db, user, student_id)

    today = today_local()
    first = datetime.date(year, month, 1)
    last = min(datetime.date(year, month, calendar.monthrange(year, month)[1]), today)

    membership_rows = group_membership_service.membership_rows_by_student(db, [student.id]).get(student.id, [])
    group_cache: dict[int, StudyGroup] = {}

    def group_on(day: datetime.date) -> StudyGroup:
        group_id = group_membership_service.resolve_group_id(membership_rows, day) or student.study_group_id
        if group_id not in group_cache:
            group_cache[group_id] = db.get(StudyGroup, group_id)
        return group_cache[group_id]

    all_days = [first + datetime.timedelta(days=i) for i in range((last - first).days + 1)] if first <= last else []

    marks: dict[datetime.date, AttendanceMark] = {}
    submitted: set[tuple[int, datetime.date]] = set()
    if all_days:
        for m in (
            db.query(AttendanceMark)
            .filter(AttendanceMark.student_id == student.id, AttendanceMark.date >= first, AttendanceMark.date <= last)
            .all()
        ):
            marks[m.date] = m
        group_ids = {group_on(d).id for d in all_days}
        submitted = {
            (s.study_group_id, s.date)
            for s in db.query(DaySubmission)
            .filter(DaySubmission.study_group_id.in_(group_ids), DaySubmission.date >= first, DaySubmission.date <= last)
            .all()
        }

    days: list[StudentDayAttendance] = []
    counts = {"study_days": 0, "present": 0, "absent": 0, "excused": 0, "unexcused": 0, "late": 0, "not_submitted": 0}
    by_code: dict[str, int] = {}

    for current in all_days:
        group = group_on(current)
        enrolled = student.enrolled_at <= current and (student.left_at is None or student.left_at >= current)
        day_type = calendar_service.resolve_day_type(db, current, study_group_id=group.id, course=group.course)
        mark = marks.get(current)

        if not enrolled and mark is None:
            days.append(StudentDayAttendance(date=current, day_type="not_enrolled", status="none", group_code=group.code))
        elif day_type not in _ATTENDABLE and mark is None:
            days.append(StudentDayAttendance(date=current, day_type=day_type.value, status="none", group_code=group.code))
        elif mark is not None:
            code = mark.mark_code
            days.append(
                StudentDayAttendance(
                    date=current, day_type=day_type.value, status="mark", group_code=group.code,
                    mark_code=code.code, mark_name=code.name, counts_as_present=code.counts_as_present,
                    is_excused=code.is_excused, comment=mark.comment, basis_reference=mark.basis_reference,
                )
            )
            counts["study_days"] += 1
            by_code[code.code] = by_code.get(code.code, 0) + 1
            if code.code == "о":
                counts["late"] += 1
            if code.counts_as_present:
                counts["present"] += 1
            else:
                counts["absent"] += 1
                counts["excused" if code.is_excused else "unexcused"] += 1
        elif (group.id, current) in submitted:
            days.append(StudentDayAttendance(date=current, day_type=day_type.value, status="present", group_code=group.code))
            counts["study_days"] += 1
            counts["present"] += 1
        else:
            days.append(
                StudentDayAttendance(date=current, day_type=day_type.value, status="not_submitted", group_code=group.code)
            )
            counts["not_submitted"] += 1

    counted = counts["study_days"]
    return StudentMonthAttendance(
        student_id=student.id, year=year, month=month, first_month=student.enrolled_at.strftime("%Y-%m"),
        summary=StudentMonthSummary(
            study_days=counted, present=counts["present"], absent=counts["absent"],
            absent_excused=counts["excused"], absent_unexcused=counts["unexcused"], late=counts["late"],
            not_submitted=counts["not_submitted"],
            percent=round(counts["present"] / counted * 100, 2) if counted else None,
            by_code=by_code,
        ),
        days=days,
    )
