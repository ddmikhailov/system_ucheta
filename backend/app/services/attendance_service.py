import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import utcnow
from app.models import (
    AbsencePeriod,
    AttendanceMark,
    BasisStatus,
    DaySubmission,
    MarkCode,
    MarkSource,
    Student,
    StudentStatus,
    User,
)
from app.services import calendar_service
from app.services.audit_service import log_action

settings = get_settings()


class BackdateNotAllowed(Exception):
    pass


def _compute_basis(basis_reference: str | None) -> tuple[BasisStatus, None]:
    """Основание (номер приказа/справки) — необязательное дополнение к коду
    отметки, а не обязательное условие (см. обновление 1.1: убран жёсткий
    контроль дедлайна подтверждения — куратор может указать документ, но
    его отсутствие ни к чему не обязывает и никого не блокирует)."""
    return (BasisStatus.CONFIRMED if basis_reference else BasisStatus.NOT_REQUIRED), None


def get_active_students(db: Session, study_group_id: int, as_of: datetime.date) -> list[Student]:
    stmt = (
        select(Student)
        .where(
            Student.study_group_id == study_group_id,
            Student.enrolled_at <= as_of,
        )
        .where((Student.left_at.is_(None)) | (Student.left_at >= as_of))
        .order_by(Student.last_name, Student.first_name)
    )
    return list(db.execute(stmt).scalars().all())


def can_backdate(user: User, target_date: datetime.date, today: datetime.date) -> bool:
    from app.models.enums import RoleCode

    if user.role.code in (RoleCode.DEPT_HEAD, RoleCode.EDU_DEPARTMENT, RoleCode.ADMIN):
        return True
    earliest_editable = today - datetime.timedelta(days=settings.curator_backdate_days)
    return earliest_editable <= target_date <= today


def get_mark_codes(db: Session) -> dict[str, MarkCode]:
    rows = db.execute(select(MarkCode).where(MarkCode.is_active.is_(True))).scalars().all()
    return {row.code: row for row in rows}


def consecutive_unexcused_count(
    db: Session, student_id: int, as_of_date: datetime.date, lookback_days: int = 21
) -> int:
    """Сколько учебных дней подряд перед as_of_date (не включая) стоит код 'н'."""
    window_start = as_of_date - datetime.timedelta(days=lookback_days)
    study_days = calendar_service.study_days_between(db, window_start, as_of_date - datetime.timedelta(days=1))
    if not study_days:
        return 0
    study_days.sort(reverse=True)

    marks = db.execute(
        select(AttendanceMark.date, MarkCode.code)
        .join(MarkCode, MarkCode.id == AttendanceMark.mark_code_id)
        .where(AttendanceMark.student_id == student_id, AttendanceMark.date.in_(study_days))
    ).all()
    marks_by_date = {row.date: row.code for row in marks}

    streak = 0
    for day in study_days:
        if marks_by_date.get(day) == "н":
            streak += 1
        else:
            break
    return streak


def get_roster(db: Session, study_group_id: int, date: datetime.date) -> dict:
    active_students = get_active_students(db, study_group_id, date)
    student_ids = [s.id for s in active_students]

    submission = db.execute(
        select(DaySubmission).where(
            DaySubmission.study_group_id == study_group_id, DaySubmission.date == date
        )
    ).scalar_one_or_none()

    existing_marks: dict[int, AttendanceMark] = {}
    if student_ids:
        rows = db.execute(
            select(AttendanceMark).where(
                AttendanceMark.student_id.in_(student_ids), AttendanceMark.date == date
            )
        ).scalars().all()
        existing_marks = {row.student_id: row for row in rows}

    draft_marks: dict[int, AttendanceMark] = {}
    is_draft = submission is None
    if is_draft and student_ids:
        prev_day = calendar_service.previous_study_day(db, date)
        if prev_day is not None:
            rows = db.execute(
                select(AttendanceMark).where(
                    AttendanceMark.student_id.in_(student_ids), AttendanceMark.date == prev_day
                )
            ).scalars().all()
            draft_marks = {row.student_id: row for row in rows}

    entries = []
    for student in active_students:
        mark = existing_marks.get(student.id)
        source_is_draft = False
        if mark is None and is_draft:
            draft = draft_marks.get(student.id)
            if draft is not None:
                mark = draft
                source_is_draft = True

        risk_streak = consecutive_unexcused_count(db, student.id, date)

        entries.append(
            {
                "student_id": student.id,
                "full_name": student.full_name,
                "mark_code": mark.mark_code.code if mark else None,
                "mark_name": mark.mark_code.name if mark else None,
                "comment": mark.comment if mark else None,
                "basis_reference": mark.basis_reference if mark else None,
                "is_draft_suggestion": source_is_draft,
                "is_locked": bool(mark and mark.source == MarkSource.PERIOD),
                "risk_streak": risk_streak,
            }
        )

    return {
        "study_group_id": study_group_id,
        "date": date,
        "is_submitted": submission is not None,
        "submitted_at": submission.submitted_at if submission else None,
        "is_on_time": submission.is_on_time if submission else None,
        "entries": entries,
    }


def submit_day(
    db: Session,
    study_group_id: int,
    date: datetime.date,
    exceptions: list[dict],
    user: User,
    today: datetime.date | None = None,
) -> DaySubmission:
    today = today or datetime.date.today()
    if not can_backdate(user, date, today):
        raise BackdateNotAllowed(
            f"Правка за {date} недоступна: куратор редактирует только текущий и "
            f"предыдущий учебный день, дальше — через зав. отделением."
        )

    mark_codes = get_mark_codes(db)
    active_students = get_active_students(db, study_group_id, date)
    active_ids = {s.id for s in active_students}

    existing_marks = {
        row.student_id: row
        for row in db.execute(
            select(AttendanceMark).where(
                AttendanceMark.student_id.in_(active_ids),
                AttendanceMark.date == date,
            )
        ).scalars().all()
    }

    exceptions_by_student = {e["student_id"]: e for e in exceptions if e["student_id"] in active_ids}

    for student_id in active_ids:
        entry = exceptions_by_student.get(student_id)
        existing = existing_marks.get(student_id)

        if existing is not None and existing.source == MarkSource.PERIOD and entry is None:
            continue

        if entry is None:
            if existing is not None:
                log_action(db, user, "mark.delete", "attendance_mark", str(existing.id), old_value=existing.mark_code.code)
                db.delete(existing)
            continue

        mark_code = mark_codes.get(entry["mark_code"])
        if mark_code is None:
            continue

        basis_reference = entry.get("basis_reference")
        basis_status, basis_deadline = _compute_basis(basis_reference)

        if existing is not None:
            old_code = existing.mark_code.code
            existing.mark_code_id = mark_code.id
            existing.comment = entry.get("comment")
            existing.basis_reference = basis_reference
            existing.basis_status = basis_status
            existing.basis_deadline = basis_deadline
            existing.source = MarkSource.MANUAL
            existing.updated_by_user_id = user.id
            existing.updated_at = utcnow()
            log_action(db, user, "mark.update", "attendance_mark", str(existing.id), old_value=old_code, new_value=mark_code.code)
        else:
            new_mark = AttendanceMark(
                student_id=student_id,
                date=date,
                mark_code_id=mark_code.id,
                comment=entry.get("comment"),
                source=MarkSource.MANUAL,
                basis_reference=basis_reference,
                basis_status=basis_status,
                basis_deadline=basis_deadline,
                created_by_user_id=user.id,
            )
            db.add(new_mark)
            db.flush()
            log_action(db, user, "mark.create", "attendance_mark", str(new_mark.id), new_value=mark_code.code)

    submission = db.execute(
        select(DaySubmission).where(
            DaySubmission.study_group_id == study_group_id, DaySubmission.date == date
        )
    ).scalar_one_or_none()

    # Жёсткого дедлайна на сдачу нет (см. концепцию про бота), поэтому "вовремя" здесь
    # означает "сдано в день занятия", а не до конкретного часа.
    is_on_time = date == today

    if submission is None:
        submission = DaySubmission(
            study_group_id=study_group_id,
            date=date,
            submitted_by_user_id=user.id,
            submitted_at=utcnow(),
            is_on_time=is_on_time,
        )
        db.add(submission)
        log_action(db, user, "day.submit", "day_submission", f"{study_group_id}:{date}")
    else:
        submission.submitted_by_user_id = user.id
        submission.submitted_at = utcnow()
        submission.is_on_time = is_on_time
        log_action(db, user, "day.resubmit", "day_submission", f"{study_group_id}:{date}")

    db.commit()
    return submission


def create_absence_period(
    db: Session,
    student_id: int,
    mark_code_id: int,
    date_from: datetime.date,
    date_to: datetime.date,
    basis_reference: str | None,
    user: User,
) -> AbsencePeriod:
    mark_code = db.get(MarkCode, mark_code_id)
    if mark_code is None:
        raise ValueError("Неизвестный код отметки")

    period = AbsencePeriod(
        student_id=student_id,
        mark_code_id=mark_code_id,
        date_from=date_from,
        date_to=date_to,
        basis_reference=basis_reference,
        created_by_user_id=user.id,
    )
    db.add(period)
    db.flush()

    study_days = calendar_service.study_days_between(db, date_from, date_to)

    basis_status, basis_deadline = _compute_basis(basis_reference)

    for day in study_days:
        existing = db.execute(
            select(AttendanceMark).where(
                AttendanceMark.student_id == student_id, AttendanceMark.date == day
            )
        ).scalar_one_or_none()

        if existing is not None:
            old_code = existing.mark_code.code
            existing.mark_code_id = mark_code_id
            existing.source = MarkSource.PERIOD
            existing.absence_period_id = period.id
            existing.basis_reference = basis_reference
            existing.basis_status = basis_status
            existing.basis_deadline = basis_deadline
            existing.updated_by_user_id = user.id
            existing.updated_at = utcnow()
            log_action(
                db, user, "period.overwrite_mark", "attendance_mark", str(existing.id),
                old_value=old_code, new_value=mark_code.code,
            )
        else:
            new_mark = AttendanceMark(
                student_id=student_id,
                date=day,
                mark_code_id=mark_code_id,
                source=MarkSource.PERIOD,
                absence_period_id=period.id,
                basis_reference=basis_reference,
                basis_status=basis_status,
                basis_deadline=basis_deadline,
                created_by_user_id=user.id,
            )
            db.add(new_mark)

    log_action(db, user, "period.create", "absence_period", str(period.id), new_value=mark_code.code)
    db.commit()
    return period
