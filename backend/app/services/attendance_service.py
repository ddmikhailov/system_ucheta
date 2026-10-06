import datetime
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core import policies
from app.core.config import get_settings
from app.core.time import today_local, utcnow
from app.models import (
    AbsencePeriod,
    AttendanceMark,
    BasisStatus,
    DaySubmission,
    MarkCode,
    MarkSource,
    Student,
    StudyGroup,
    User,
)
from app.services import calendar_service, group_membership_service, in_app_notification_service
from app.services.audit_service import log_action


MIN_FIRST_PERIOD = 1
MAX_FIRST_PERIOD = 10


class BackdateNotAllowed(Exception):
    pass


class InvalidSubmission(Exception):
    """Неизвестный код отметки или студент не из этой группы — раньше и то,
    и другое молча отбрасывалось, и пользователь думал, что сохранил (см.
    TODO.md 3)."""

    pass


def _compute_basis(basis_reference: str | None) -> BasisStatus:
    """Основание (номер приказа/справки) — необязательное дополнение к коду
    отметки, а не обязательное условие (см. обновление 1.1: убран жёсткий
    контроль дедлайна подтверждения — куратор может указать документ, но
    его отсутствие ни к чему не обязывает и никого не блокирует)."""
    return BasisStatus.CONFIRMED if basis_reference else BasisStatus.NOT_REQUIRED


def get_active_students(db: Session, study_group_id: int, as_of: datetime.date) -> list[Student]:
    """Ростер группы на конкретную дату — по историческому членству
    (`student_group_memberships`), а не по текущему `Student.study_group_id`
    (см. TODO.md 3): иначе бэкдейтинг посещаемости в группе, из которой
    студент с тех пор перевёлся, молча терял его из ростера того дня."""
    member_ids = group_membership_service.students_ever_in_group(db, study_group_id, as_of, as_of)
    if not member_ids:
        return []
    stmt = (
        select(Student)
        .where(
            Student.id.in_(member_ids),
            Student.enrolled_at <= as_of,
        )
        .where((Student.left_at.is_(None)) | (Student.left_at >= as_of))
        .order_by(Student.last_name, Student.first_name)
    )
    return list(db.execute(stmt).scalars().all())


def can_edit_date(user: User, target_date: datetime.date, today: datetime.date) -> bool:
    """Любая роль правит посещаемость за любой прошедший день без ограничения
    (обновление 1.1: раньше было только «вчера», теперь — весь период;
    правка задним числом больше чем на 48 часов просто уведомляет зав.
    отделением, см. notify_if_late_edit, а не блокируется). Будущее
    недоступно никому, включая администрацию (см. TODO.md 3 — раньше этот
    же docstring обещал это, а код давал admin/tutor/dept_head/edu_department
    исключение и молча пропускал проверку)."""
    return target_date <= today


def notify_if_late_edit(
    db: Session, group: StudyGroup, user: User, date: datetime.date, today: datetime.date | None = None,
) -> None:
    if user.role.code not in policies.CURATOR_CAPABLE_ROLES:
        return
    today = today or today_local()
    # Дневная гранулярность, как и everywhere в этом модуле (can_edit_date,
    # is_on_time): "больше 48 часов" здесь — день до вчерашнего и раньше.
    # Ровно "вчера" (до 48 ч) уведомление не создаёт.
    hours_late = (today - date).days * 24
    if hours_late > 48:
        in_app_notification_service.notify_late_edit(db, group, user, date, hours_late)


def get_mark_codes(db: Session) -> dict[str, MarkCode]:
    rows = db.execute(select(MarkCode).where(MarkCode.is_active.is_(True))).scalars().all()
    return {row.code: row for row in rows}


def consecutive_unexcused_count(
    db: Session,
    student_id: int,
    as_of_date: datetime.date,
    lookback_days: int = 21,
    study_group_id: int | None = None,
) -> int:
    """Сколько учебных дней подряд перед as_of_date (не включая) стоит код 'н'.

    `study_group_id` — необязательная оптимизация (см. TODO.md 5): вызывающий
    код почти всегда уже держит объект Student в цикле, и без этого параметра
    функция заново шла бы в БД за тем же id группы на каждого из ~1000
    студентов колледжа (это была заметная доля тех самых N+1 запросов на
    экране «Группа риска»)."""
    window_start = as_of_date - datetime.timedelta(days=lookback_days)
    if study_group_id is None:
        student = db.get(Student, student_id)
        study_group_id = student.study_group_id if student else None
    study_days = calendar_service.study_days_between(
        db, window_start, as_of_date - datetime.timedelta(days=1), study_group_id=study_group_id
    )
    if not study_days:
        return 0
    study_days.sort(reverse=True)

    marks = db.execute(
        select(AttendanceMark.date, MarkCode.code)
        .join(MarkCode, MarkCode.id == AttendanceMark.mark_code_id)
        .where(AttendanceMark.student_id == student_id, AttendanceMark.date.in_(study_days))
    ).all()
    marks_by_date = {row.date: row.code for row in marks}
    return _streak_from_marks(study_days, marks_by_date)


def _streak_from_marks(study_days: list[datetime.date], marks_by_date: dict[datetime.date, str]) -> int:
    streak = 0
    for day in study_days:
        if marks_by_date.get(day) == "н":
            streak += 1
        else:
            break
    return streak


def consecutive_unexcused_counts_bulk(
    db: Session, students: list[Student], as_of_date: datetime.date, lookback_days: int = 21
) -> dict[int, int]:
    """То же, что `consecutive_unexcused_count`, но сразу для списка студентов
    — было ~4 запроса на каждого из под-тысячи студентов колледжа на экране
    «Группа риска» (см. TODO.md 5: самый тяжёлый случай N+1 из ревью, 3959
    запросов). Группируем по study_group_id: учебные дни для периода
    одинаковы у всех студентов одной группы, а отметки можно выбрать одним
    запросом на группу вместо одного на студента."""
    window_end = as_of_date - datetime.timedelta(days=1)
    window_start = as_of_date - datetime.timedelta(days=lookback_days)

    by_group: dict[int | None, list[Student]] = {}
    for student in students:
        by_group.setdefault(student.study_group_id, []).append(student)
    if not by_group:
        return {}

    # Учебные дни всех групп — за два запроса, отметки всех студентов окна — за один
    # (раньше на каждую группу уходило по три запроса).
    groups = [group_students[0].study_group for group_students in by_group.values()]
    study_days_by_group = calendar_service.study_days_by_group(db, window_start, window_end, groups)

    student_ids = [s.id for s in students]
    marks_by_student: dict[int, dict[datetime.date, str]] = {}
    if student_ids:
        for row in db.execute(
            select(AttendanceMark.student_id, AttendanceMark.date, MarkCode.code)
            .join(MarkCode, MarkCode.id == AttendanceMark.mark_code_id)
            .where(
                AttendanceMark.student_id.in_(student_ids),
                AttendanceMark.date >= window_start,
                AttendanceMark.date <= window_end,
            )
        ).all():
            marks_by_student.setdefault(row.student_id, {})[row.date] = row.code

    result: dict[int, int] = {}
    for study_group_id, group_students in by_group.items():
        study_days = sorted(study_days_by_group[study_group_id], reverse=True)
        for student in group_students:
            result[student.id] = _streak_from_marks(study_days, marks_by_student.get(student.id, {})) if study_days else 0

    return result


@dataclass(frozen=True)
class AttendanceRate:
    """Посещаемость студента с начала семестра: сданные группой дни, пропущенные из них, процент."""
    days: int
    absent: int
    percent: float | None  # None — сданных дней ещё нет

    @property
    def is_risk(self) -> bool:
        """Группа риска: посещаемость ниже порога (и сданных дней уже достаточно, чтобы процент что-то значил)."""
        settings = get_settings()
        return self.percent is not None and self.days >= settings.risk_min_days and self.percent < settings.risk_attendance_percent


def semester_start(day: datetime.date) -> datetime.date:
    """Начало семестра, в который попадает `day`: сентябрь–январь — с 1 сентября, февраль–август — с 1 февраля."""
    if day.month >= 9:
        return datetime.date(day.year, 9, 1)
    if day.month == 1:
        return datetime.date(day.year - 1, 9, 1)
    return datetime.date(day.year, 2, 1)


def attendance_rates_bulk(db: Session, students: list[Student], as_of_date: datetime.date) -> dict[int, AttendanceRate]:
    """Посещаемость сразу для списка студентов — по сданным дням группы с начала семестра по `as_of_date` включительно.
    Пропуск — любая отметка, которая не считается присутствием (опоздание — присутствие); пропуски по уважительной
    причине тоже считаются, как в «Витринах». Три запроса независимо от числа студентов и групп."""
    if not students:
        return {}
    start = semester_start(as_of_date)
    group_ids = {s.study_group_id for s in students}
    submitted: dict[int, set[datetime.date]] = {gid: set() for gid in group_ids}
    for row in db.execute(
        select(DaySubmission.study_group_id, DaySubmission.date)
        .where(DaySubmission.study_group_id.in_(group_ids), DaySubmission.date >= start, DaySubmission.date <= as_of_date)
    ).all():
        submitted[row.study_group_id].add(row.date)

    absent: dict[int, set[datetime.date]] = {}
    for row in db.execute(
        select(AttendanceMark.student_id, AttendanceMark.date)
        .join(MarkCode, MarkCode.id == AttendanceMark.mark_code_id)
        .where(
            AttendanceMark.student_id.in_([s.id for s in students]),
            AttendanceMark.date >= start, AttendanceMark.date <= as_of_date,
            MarkCode.counts_as_present.is_(False),
        )
    ).all():
        absent.setdefault(row.student_id, set()).add(row.date)

    result: dict[int, AttendanceRate] = {}
    for student in students:
        days = {d for d in submitted[student.study_group_id] if d >= student.enrolled_at}
        missed = len(absent.get(student.id, set()) & days)
        result[student.id] = AttendanceRate(
            days=len(days), absent=missed, percent=round((len(days) - missed) / len(days) * 100, 1) if days else None,
        )
    return result


def count_manual_exceptions(db: Session, study_group_id: int, date: datetime.date) -> int:
    """Сколько ручных отметок на этот день будет молча стёрто, если вызвать
    submit_day с пустым списком исключений ("Все присутствуют") — см.
    TODO.md 1.8. Отметки из длительных периодов (MarkSource.PERIOD) сюда не
    входят: submit_day их и так не трогает."""
    active_ids = {s.id for s in get_active_students(db, study_group_id, date)}
    if not active_ids:
        return 0
    return db.execute(
        select(func.count())
        .select_from(AttendanceMark)
        .where(
            AttendanceMark.student_id.in_(active_ids),
            AttendanceMark.date == date,
            AttendanceMark.source == MarkSource.MANUAL,
        )
    ).scalar_one()


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
            select(AttendanceMark)
            .options(joinedload(AttendanceMark.mark_code))
            .where(AttendanceMark.student_id.in_(student_ids), AttendanceMark.date == date)
        ).scalars().all()
        existing_marks = {row.student_id: row for row in rows}

    draft_marks: dict[int, AttendanceMark] = {}
    is_draft = submission is None
    if is_draft and student_ids:
        prev_day = calendar_service.previous_study_day(db, date, study_group_id=study_group_id)
        if prev_day is not None:
            rows = db.execute(
                select(AttendanceMark)
                .options(joinedload(AttendanceMark.mark_code))
                .where(AttendanceMark.student_id.in_(student_ids), AttendanceMark.date == prev_day)
            ).scalars().all()
            draft_marks = {row.student_id: row for row in rows}

    actor_ids = {
        actor_id
        for mark in existing_marks.values()
        for actor_id in (mark.updated_by_user_id, mark.created_by_user_id)
        if actor_id is not None
    }
    actor_names: dict[int, str] = {}
    if actor_ids:
        actor_names = {
            u.id: u.full_name
            for u in db.execute(select(User).where(User.id.in_(actor_ids))).scalars()
        }

    # Серии неуважительных пропусков всех студентов группы — разом, а не по четыре запроса на студента.
    risk_streaks = consecutive_unexcused_counts_bulk(db, active_students, date)
    rates = attendance_rates_bulk(db, active_students, date)

    entries = []
    for student in active_students:
        mark = existing_marks.get(student.id)
        source_is_draft = False
        if mark is None and is_draft:
            draft = draft_marks.get(student.id)
            if draft is not None:
                mark = draft
                source_is_draft = True

        risk_streak = risk_streaks.get(student.id, 0)

        last_edited_by = None
        last_edited_at = None
        # Для черновика со вчера "кто менял" относится к вчерашней отметке —
        # только запутает в журнале сегодняшнего дня, поэтому не показываем.
        if mark is not None and not source_is_draft:
            actor_id = mark.updated_by_user_id or mark.created_by_user_id
            last_edited_by = actor_names.get(actor_id)
            last_edited_at = mark.updated_at or mark.created_at

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
                "attendance_percent": rates[student.id].percent,
                "is_risk": rates[student.id].is_risk,
                "last_edited_by": last_edited_by,
                "last_edited_at": last_edited_at,
            }
        )

    return {
        "study_group_id": study_group_id,
        "date": date,
        "is_submitted": submission is not None,
        "submitted_at": submission.submitted_at if submission else None,
        "is_on_time": submission.is_on_time if submission else None,
        "first_period": submission.first_period if submission else None,
        "entries": entries,
    }


def submit_day(
    db: Session,
    study_group_id: int,
    date: datetime.date,
    exceptions: list[dict],
    user: User,
    today: datetime.date | None = None,
    first_period: int | None = None,
) -> DaySubmission:
    if first_period is not None and not (MIN_FIRST_PERIOD <= first_period <= MAX_FIRST_PERIOD):
        raise InvalidSubmission(
            f"Пара должна быть от {MIN_FIRST_PERIOD} до {MAX_FIRST_PERIOD}, получено {first_period}"
        )
    today = today or today_local()
    if not can_edit_date(user, date, today):
        raise BackdateNotAllowed(f"Правка за {date} недоступна: это ещё не наступивший день.")

    group = db.get(StudyGroup, study_group_id)
    if group is not None and not calendar_service.is_study_day(
        db, date, study_group_id=study_group_id, course=group.course
    ):
        # Нет занятия — нечего отмечать (см. TODO.md 3: раньше можно было
        # "сдать" выходной/праздник/каникулы как обычный учебный день).
        raise BackdateNotAllowed(f"{date} — нерабочий день, отмечать посещаемость не нужно.")

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

    for entry in exceptions:
        if entry["student_id"] not in active_ids:
            raise InvalidSubmission(f"Студент {entry['student_id']} не из этой группы на {date}")
        if entry["mark_code"] not in mark_codes:
            raise InvalidSubmission(f"Неизвестный код отметки: {entry['mark_code']!r}")

    exceptions_by_student = {e["student_id"]: e for e in exceptions}

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

        mark_code = mark_codes[entry["mark_code"]]

        basis_reference = entry.get("basis_reference")
        basis_status = _compute_basis(basis_reference)

        if existing is not None:
            old_code = existing.mark_code.code
            existing.mark_code_id = mark_code.id
            existing.comment = entry.get("comment")
            existing.basis_reference = basis_reference
            existing.basis_status = basis_status
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
            first_period=first_period,
        )
        db.add(submission)
        log_action(db, user, "day.submit", "day_submission", f"{study_group_id}:{date}")
    else:
        submission.submitted_by_user_id = user.id
        submission.submitted_at = utcnow()
        submission.is_on_time = is_on_time
        # None — «не менять»: повторная сдача (например, «Все присутствуют»
        # без выбора пары) не должна стирать уже выставленную пару.
        if first_period is not None:
            submission.first_period = first_period
        log_action(db, user, "day.resubmit", "day_submission", f"{study_group_id}:{date}")

    group = db.get(StudyGroup, study_group_id)
    if group is not None:
        notify_if_late_edit(db, group, user, date, today=today)

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

    student = db.get(Student, student_id)
    study_days = calendar_service.study_days_between(
        db, date_from, date_to, study_group_id=student.study_group_id if student else None
    )

    basis_status = _compute_basis(basis_reference)

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
                created_by_user_id=user.id,
            )
            db.add(new_mark)

    log_action(db, user, "period.create", "absence_period", str(period.id), new_value=mark_code.code)
    db.commit()
    return period
