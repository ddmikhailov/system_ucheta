"""«Восполнить пропуски» (решение 21.10.2026): студенты группы, которые пропустили учебный процесс по уважительной
причине (или без неё, но меньше порога группы риска) и должны догнать программу. Практика и ИУП сюда не идут — флаг
кода `no_compensation`. Куратор сам закрывает «Восполнить пропуски» комментарием (как и чем восполнено).

Критерий — `AttendanceRate.needs_compensation` (attendance_service)."""
import datetime
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AbsenceCompensation, AttendanceMark, DaySubmission, MarkCode, Student, User
from app.services import attendance_service
from app.services.audit_service import log_action


class NothingToClose(Exception):
    pass


@dataclass
class CompensationRow:
    student_id: int
    full_name: str
    attendance_percent: float | None
    days: int
    absent_to_compensate: int
    # Пропуски, которые нужно восполнить, по видам отметок: [(«Больничный лист», 10), …], от частых к редким.
    by_mark: list[tuple[str, int]] = field(default_factory=list)
    last_closed_on: datetime.date | None = None


@dataclass
class ClosedRow:
    student_id: int
    full_name: str
    closed_on: datetime.date
    comment: str
    author_name: str | None


def group_overview(db: Session, group_id: int, today: datetime.date) -> tuple[list[CompensationRow], list[ClosedRow]]:
    """Кому в группе нужно восполнить пропуски (сначала — у кого посещаемость хуже) и что уже закрыто в этом семестре."""
    students = attendance_service.get_active_students(db, group_id, today)
    if not students:
        return [], []
    rates = attendance_service.attendance_rates_bulk(db, students, today)
    start = attendance_service.semester_start(today)
    names = {s.id: s.full_name for s in students}

    pending = [s for s in students if rates[s.id].needs_compensation]
    by_mark: dict[int, dict[str, int]] = {}
    if pending:
        submitted = set(db.scalars(
            select(DaySubmission.date)
            .where(DaySubmission.study_group_id == group_id, DaySubmission.date >= start, DaySubmission.date <= today)
        ))
        enrolled = {s.id: s.enrolled_at for s in pending}
        for row in db.execute(
            select(AttendanceMark.student_id, AttendanceMark.date, MarkCode.name)
            .join(MarkCode, MarkCode.id == AttendanceMark.mark_code_id)
            .where(
                AttendanceMark.student_id.in_(list(enrolled)),
                AttendanceMark.date >= start, AttendanceMark.date <= today,
                MarkCode.counts_as_present.is_(False), MarkCode.no_compensation.is_(False),
            )
        ).all():
            if row.date in submitted and row.date >= enrolled[row.student_id]:
                counts = by_mark.setdefault(row.student_id, {})
                counts[row.name] = counts.get(row.name, 0) + 1

    rows = [
        CompensationRow(
            student_id=s.id, full_name=s.full_name, attendance_percent=rates[s.id].percent, days=rates[s.id].days,
            absent_to_compensate=rates[s.id].absent_to_compensate,
            by_mark=sorted(by_mark.get(s.id, {}).items(), key=lambda item: (-item[1], item[0])),
            last_closed_on=rates[s.id].compensation_closed_on,
        )
        for s in pending
    ]
    rows.sort(key=lambda r: (r.attendance_percent if r.attendance_percent is not None else 101.0, r.full_name))

    closed_rows = db.execute(
        select(AbsenceCompensation, User.full_name)
        .outerjoin(User, User.id == AbsenceCompensation.created_by_user_id)
        .where(
            AbsenceCompensation.student_id.in_(list(names)),
            AbsenceCompensation.closed_on >= start, AbsenceCompensation.closed_on <= today,
        )
        .order_by(AbsenceCompensation.closed_on.desc(), AbsenceCompensation.id.desc())
    ).all()
    closed = [
        ClosedRow(student_id=c.student_id, full_name=names[c.student_id], closed_on=c.closed_on, comment=c.comment,
                  author_name=author)
        for c, author in closed_rows
    ]
    return rows, closed


def close(db: Session, user: User, student: Student, group_id: int, comment: str, today: datetime.date) -> AbsenceCompensation:
    """Куратор закрывает «Восполнить пропуски»: пропуски по сегодняшний день восполнены. Закрыть можно, только пока
    студент в этом списке, — иначе комментарий повис бы без повода."""
    comment = comment.strip()
    if not comment:
        raise ValueError("Напишите, как восполнены пропуски")
    in_group = {s.id for s in attendance_service.get_active_students(db, group_id, today)}
    if student.id not in in_group:
        raise NothingToClose("Студент не числится в этой группе")
    rate = attendance_service.attendance_rates_bulk(db, [student], today)[student.id]
    if not rate.needs_compensation:
        raise NothingToClose("Этому студенту сейчас не нужно восполнять пропуски")
    record = AbsenceCompensation(student_id=student.id, closed_on=today, comment=comment, created_by_user_id=user.id)
    db.add(record)
    db.flush()
    log_action(db, user, "absence_compensation.close", "student", str(student.id), new_value=f"closed_on={today}")
    db.commit()
    return record
