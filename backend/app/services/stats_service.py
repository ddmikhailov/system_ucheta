import datetime
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceMark,
    DaySubmission,
    MarkCode,
    Student,
    StudyGroup,
)
from app.services import calendar_service


@dataclass
class PeriodStats:
    in_list: int = 0
    absent_total: int = 0
    absent_excused: int = 0
    absent_unexcused: int = 0
    late: int = 0
    by_code: dict[str, int] = field(default_factory=dict)

    @property
    def present(self) -> int:
        return self.in_list - self.absent_total

    @property
    def percent(self) -> float:
        if self.in_list == 0:
            return 0.0
        return round(self.present / self.in_list * 100, 2)


def _students_in_scope(
    db: Session,
    department_id: int | None = None,
    course: int | None = None,
    study_group_id: int | None = None,
    student_id: int | None = None,
) -> list[Student]:
    stmt = select(Student).join(StudyGroup, StudyGroup.id == Student.study_group_id)
    if student_id is not None:
        stmt = stmt.where(Student.id == student_id)
    if study_group_id is not None:
        stmt = stmt.where(Student.study_group_id == study_group_id)
    if course is not None:
        stmt = stmt.where(StudyGroup.course == course)
    if department_id is not None:
        stmt = stmt.where(StudyGroup.department_id == department_id)
    return list(db.execute(stmt).scalars().all())


def compute_period_stats(
    db: Session,
    date_from: datetime.date,
    date_to: datetime.date,
    department_id: int | None = None,
    course: int | None = None,
    study_group_id: int | None = None,
    student_id: int | None = None,
    only_submitted: bool = False,
) -> PeriodStats:
    """only_submitted=True считает "в списке" только по дням, которые группа
    реально сдала — иначе несданный день молча учитывался как 100%
    присутствия (см. TODO.md 3: пустой день без единой отметки давал
    present == in_list)."""
    students = _students_in_scope(db, department_id, course, study_group_id, student_id)
    if not students:
        return PeriodStats()

    effective_group_id = study_group_id
    if effective_group_id is None and student_id is not None and len(students) == 1:
        effective_group_id = students[0].study_group_id
    study_days = calendar_service.study_days_between(
        db, date_from, date_to, study_group_id=effective_group_id, course=course
    )
    if not study_days:
        return PeriodStats()

    student_ids = [s.id for s in students]
    student_by_id = {s.id: s for s in students}

    submitted_pairs: set[tuple[int, datetime.date]] | None = None
    if only_submitted:
        group_ids = {s.study_group_id for s in students}
        submission_rows = db.execute(
            select(DaySubmission.study_group_id, DaySubmission.date).where(
                DaySubmission.study_group_id.in_(group_ids), DaySubmission.date.in_(study_days)
            )
        ).all()
        submitted_pairs = {(r.study_group_id, r.date) for r in submission_rows}

    marks = db.execute(
        select(AttendanceMark.student_id, AttendanceMark.date, MarkCode.code, MarkCode.counts_as_present, MarkCode.is_excused)
        .join(MarkCode, MarkCode.id == AttendanceMark.mark_code_id)
        .where(AttendanceMark.student_id.in_(student_ids), AttendanceMark.date.in_(study_days))
    ).all()

    stats = PeriodStats()
    study_days_set = set(study_days)

    for student in students:
        enrolled_days = {
            d for d in study_days_set
            if student.enrolled_at <= d and (student.left_at is None or student.left_at >= d)
            and (submitted_pairs is None or (student.study_group_id, d) in submitted_pairs)
        }
        stats.in_list += len(enrolled_days)

    for row in marks:
        if submitted_pairs is not None:
            student = student_by_id.get(row.student_id)
            if student is None or (student.study_group_id, row.date) not in submitted_pairs:
                continue
        stats.by_code[row.code] = stats.by_code.get(row.code, 0) + 1
        if row.code == "о":
            stats.late += 1
        if not row.counts_as_present:
            stats.absent_total += 1
            if row.is_excused:
                stats.absent_excused += 1
            else:
                stats.absent_unexcused += 1

    return stats


def _current_responsible_name(group: StudyGroup, as_of: datetime.date) -> str | None:
    """Замещающий, если он сейчас активен, иначе куратор — тот же приоритет,
    что и в напоминаниях (notification_service.get_responsible_user), но без
    циклического импорта. Нужен, чтобы «Дисциплина кураторов» и «День по
    колледжу» показывали, к кому идти, а не только код группы (см. TODO.md 3)."""
    deputy = next(
        (
            a.user.full_name for a in group.curator_assignments
            if a.role_type.value == "deputy" and a.is_active_on(as_of) and a.user.is_active
        ),
        None,
    )
    if deputy:
        return deputy
    return next(
        (
            a.user.full_name for a in group.curator_assignments
            if a.role_type.value == "curator" and a.is_active_on(as_of) and a.user.is_active
        ),
        None,
    )


def day_overview(db: Session, date: datetime.date, department_id: int | None = None) -> list[dict]:
    stmt = select(StudyGroup).where(StudyGroup.is_active.is_(True))
    if department_id is not None:
        stmt = stmt.where(StudyGroup.department_id == department_id)
    groups = list(db.execute(stmt.order_by(StudyGroup.course, StudyGroup.code)).scalars().all())

    submissions = {
        row.study_group_id: row
        for row in db.execute(
            select(DaySubmission).where(
                DaySubmission.date == date,
                DaySubmission.study_group_id.in_([g.id for g in groups]),
            )
        ).scalars().all()
    }

    rows = []
    for group in groups:
        if not calendar_service.is_study_day(db, date, study_group_id=group.id, course=group.course):
            # Не учебный день у этой конкретной группы (например, суббота у
            # курса не 1, или у группы отдельное исключение календаря) — не
            # показываем как "не сдано", сдавать нечего (см. TODO.md 3).
            continue
        responsible_name = _current_responsible_name(group, date)
        submission = submissions.get(group.id)
        if submission is None:
            # День не сдан — «100% присутствия» тут means "мы ничего не
            # знаем", а не "все были". Показываем это явно как None/«—»,
            # а не задним числом рассчитанную по нулю отметок статистику.
            rows.append(
                {
                    "study_group_id": group.id, "code": group.code, "course": group.course,
                    "in_list": None, "present": None, "late": None,
                    "absent_excused": None, "absent_unexcused": None, "percent": None,
                    "is_submitted": False, "is_on_time": None, "responsible_name": responsible_name,
                }
            )
            continue
        stats = compute_period_stats(db, date, date, study_group_id=group.id)
        rows.append(
            {
                "study_group_id": group.id,
                "code": group.code,
                "course": group.course,
                "responsible_name": responsible_name,
                "in_list": stats.in_list,
                "present": stats.present,
                "late": stats.late,
                "absent_excused": stats.absent_excused,
                "absent_unexcused": stats.absent_unexcused,
                "percent": stats.percent,
                "is_submitted": True,
                "is_on_time": submission.is_on_time,
            }
        )
    return rows


def dynamics(
    db: Session,
    date_from: datetime.date,
    date_to: datetime.date,
    department_id: int | None = None,
    course: int | None = None,
    study_group_id: int | None = None,
    student_id: int | None = None,
) -> list[dict]:
    study_days = calendar_service.study_days_between(
        db, date_from, date_to, study_group_id=study_group_id, course=course
    )
    result = []
    for day in study_days:
        stats = compute_period_stats(
            db, day, day, department_id, course, study_group_id, student_id, only_submitted=True
        )
        if stats.in_list == 0:
            # Никто из группы(групп) этот день не сдал — не 100%/0%, а «нет данных».
            result.append({"date": day, "percent": None, "in_list": None, "present": None})
        else:
            result.append({"date": day, "percent": stats.percent, "in_list": stats.in_list, "present": stats.present})
    return result


def curator_discipline(
    db: Session,
    date_from: datetime.date,
    date_to: datetime.date,
    department_id: int | None = None,
) -> list[dict]:
    stmt = select(StudyGroup).where(StudyGroup.is_active.is_(True))
    if department_id is not None:
        stmt = stmt.where(StudyGroup.department_id == department_id)
    groups = list(db.execute(stmt.order_by(StudyGroup.course, StudyGroup.code)).scalars().all())

    rows = []
    for group in groups:
        study_days = calendar_service.study_days_between(
            db, date_from, date_to, study_group_id=group.id, course=group.course
        )
        submissions = db.execute(
            select(DaySubmission).where(
                DaySubmission.study_group_id == group.id,
                DaySubmission.date.in_(study_days),
            )
        ).scalars().all()
        by_date = {s.date: s for s in submissions}
        on_time = sum(1 for d in study_days if by_date.get(d) and by_date[d].is_on_time)
        late = sum(1 for d in study_days if by_date.get(d) and not by_date[d].is_on_time)
        missed = len(study_days) - on_time - late
        rows.append(
            {
                "study_group_id": group.id,
                "code": group.code,
                "course": group.course,
                "responsible_name": _current_responsible_name(group, date_to),
                "on_time": on_time,
                "late": late,
                "missed": missed,
                "total_study_days": len(study_days),
            }
        )
    return rows


def risk_students(
    db: Session,
    as_of_date: datetime.date,
    threshold: int,
    department_id: int | None = None,
) -> list[dict]:
    from app.services.attendance_service import consecutive_unexcused_counts_bulk

    students = _students_in_scope(db, department_id=department_id)
    streaks = consecutive_unexcused_counts_bulk(db, students, as_of_date + datetime.timedelta(days=1))
    rows = []
    for student in students:
        streak = streaks[student.id]
        if streak >= threshold:
            rows.append(
                {
                    "student_id": student.id,
                    "full_name": student.full_name,
                    "study_group_id": student.study_group_id,
                    "group_code": student.study_group.code,
                    "streak": streak,
                }
            )
    rows.sort(key=lambda r: -r["streak"])
    return rows
