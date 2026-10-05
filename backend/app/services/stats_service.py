import datetime
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import (
    AttendanceMark,
    CuratorAssignment,
    DaySubmission,
    MarkCode,
    Student,
    StudentGroupMembership,
    StudyGroup,
)
from app.core.time import utc_to_local
from app.services import calendar_service, group_membership_service


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
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
) -> list[Student]:
    # study_group_id + дата(ы) — историческое членство, а не текущий FK
    # (см. TODO.md 3): иначе студент, переведённый из группы в середине
    # периода, пропадал бы из её отчёта за уже прошедшие дни, а появлялся
    # бы в отчёте новой группы задним числом, хотя в те дни в ней не состоял.
    if study_group_id is not None and (date_from is not None or date_to is not None):
        as_of_from = date_from or date_to
        as_of_to = date_to or date_from
        historical_ids = group_membership_service.students_ever_in_group(
            db, study_group_id, as_of_from, as_of_to
        )
        if not historical_ids:
            return []
        stmt = select(Student).where(Student.id.in_(historical_ids))
        if student_id is not None:
            stmt = stmt.where(Student.id == student_id)
        return list(db.execute(stmt).scalars().all())

    # study_group подгружаем сразу: потребители (группа риска и др.) читают код группы
    # у каждого студента — иначе на каждого свой запрос.
    stmt = (
        select(Student)
        .join(StudyGroup, StudyGroup.id == Student.study_group_id)
        .options(joinedload(Student.study_group))
    )
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
    present == in_list).

    Группа, за которую засчитывается день, определяется историческим
    членством на эту дату (`student_group_memberships`), а не текущим
    `Student.study_group_id` — иначе перевод студента в другую группу задним
    числом переписывал бы, кому принадлежит его прошлая посещаемость (см.
    TODO.md 3)."""
    students = _students_in_scope(db, department_id, course, study_group_id, student_id, date_from, date_to)
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
    membership_by_student = group_membership_service.membership_rows_by_student(db, student_ids)

    def group_on(sid: int, d: datetime.date) -> int:
        rows = membership_by_student.get(sid)
        resolved = group_membership_service.resolve_group_id(rows, d) if rows else None
        return resolved if resolved is not None else student_by_id[sid].study_group_id

    submitted_pairs: set[tuple[int, datetime.date]] | None = None
    if only_submitted:
        group_ids = {study_group_id} if study_group_id is not None else set()
        for rows in membership_by_student.values():
            group_ids.update(r.study_group_id for r in rows)
        group_ids.discard(None)
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
        enrolled_days = set()
        for d in study_days_set:
            if not (student.enrolled_at <= d and (student.left_at is None or student.left_at >= d)):
                continue
            day_group = group_on(student.id, d)
            if study_group_id is not None and day_group != study_group_id:
                # В этот день студент состоял в другой группе — не его день
                # в ЭТОМ отчёте (см. пояснение выше).
                continue
            if submitted_pairs is not None and (day_group, d) not in submitted_pairs:
                continue
            enrolled_days.add(d)
        stats.in_list += len(enrolled_days)

    for row in marks:
        day_group = group_on(row.student_id, row.date)
        if study_group_id is not None and day_group != study_group_id:
            continue
        if submitted_pairs is not None and (day_group, row.date) not in submitted_pairs:
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
    что и в уведомлениях, но без
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


def _active_groups(db: Session, department_id: int | None = None) -> list[StudyGroup]:
    """Активные группы с куратором и замещающим — назначения и их пользователи
    подгружаются сразу (иначе на каждую группу уходит запрос на назначения и ещё
    по запросу на каждого пользователя)."""
    stmt = (
        select(StudyGroup)
        .where(StudyGroup.is_active.is_(True))
        .options(selectinload(StudyGroup.curator_assignments).selectinload(CuratorAssignment.user))
    )
    if department_id is not None:
        stmt = stmt.where(StudyGroup.department_id == department_id)
    return list(db.execute(stmt.order_by(StudyGroup.course, StudyGroup.code)).scalars().all())


def compute_day_stats_bulk(db: Session, day: datetime.date, group_ids: list[int]) -> dict[int, PeriodStats]:
    """Те же числа, что `compute_period_stats(day, day, study_group_id=...)` для каждой
    группы, но тремя запросами на все группы сразу, а не пятью на каждую.

    Группа студента на день — по членству (`student_group_memberships`), в списке
    считаются зачисленные и ещё не выбывшие, отметки — всех студентов группы на этот день."""
    stats = {gid: PeriodStats() for gid in group_ids}
    if not group_ids:
        return stats
    # Как в построчном расчёте: если у группы в этот день занятий нет (выходной по её курсу, праздник,
    # день, объявленный нерабочим задним числом), её числа — нули, даже если отметки в базе остались.
    groups = db.execute(select(StudyGroup).where(StudyGroup.id.in_(group_ids))).scalars().all()
    studying = {gid for gid, days in calendar_service.study_days_by_group(db, day, day, groups).items() if days}
    if not studying:
        return stats

    members = db.execute(
        select(StudentGroupMembership.study_group_id, Student.id, Student.enrolled_at, Student.left_at)
        .join(Student, Student.id == StudentGroupMembership.student_id)
        .where(
            StudentGroupMembership.study_group_id.in_(studying),
            StudentGroupMembership.start_date <= day,
            (StudentGroupMembership.end_date.is_(None)) | (StudentGroupMembership.end_date >= day),
        )
    ).all()
    group_of_student: dict[int, int] = {}
    for group_id, student_id, enrolled_at, left_at in members:
        # Если у студента вдруг два действующих членства — берём первое, как `resolve_group_id`.
        if student_id in group_of_student:
            continue
        group_of_student[student_id] = group_id
        if enrolled_at <= day and (left_at is None or left_at >= day):
            stats[group_id].in_list += 1

    if not group_of_student:
        return stats
    marks = db.execute(
        select(AttendanceMark.student_id, MarkCode.code, MarkCode.counts_as_present, MarkCode.is_excused)
        .join(MarkCode, MarkCode.id == AttendanceMark.mark_code_id)
        .where(AttendanceMark.student_id.in_(list(group_of_student)), AttendanceMark.date == day)
    ).all()
    for student_id, code, counts_as_present, is_excused in marks:
        group_stats = stats[group_of_student[student_id]]
        group_stats.by_code[code] = group_stats.by_code.get(code, 0) + 1
        if code == "о":
            group_stats.late += 1
        if not counts_as_present:
            group_stats.absent_total += 1
            if is_excused:
                group_stats.absent_excused += 1
            else:
                group_stats.absent_unexcused += 1
    return stats


def day_overview(db: Session, date: datetime.date, department_id: int | None = None) -> list[dict]:
    groups = _active_groups(db, department_id)

    submissions = {
        row.study_group_id: row
        for row in db.execute(
            select(DaySubmission).where(
                DaySubmission.date == date,
                DaySubmission.study_group_id.in_([g.id for g in groups]),
            )
        ).scalars().all()
    }
    # Не учебный день у этой конкретной группы (например, суббота у курса не 1, или у
    # группы отдельное исключение календаря) — не показываем как «не сдано», сдавать
    # нечего (см. TODO.md 3). Календарь всех групп — за два запроса.
    study_days = calendar_service.study_days_by_group(db, date, date, groups)
    stats_by_group = compute_day_stats_bulk(db, date, [g.id for g in groups if g.id in submissions])

    rows = []
    for group in groups:
        if not study_days[group.id]:
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
        stats = stats_by_group[group.id]
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


def _dynamics_per_day(
    db: Session,
    date_from: datetime.date,
    date_to: datetime.date,
    department_id: int | None,
    course: int | None,
    study_group_id: int | None,
    student_id: int | None,
) -> list[dict]:
    """Общий случай: на каждый день — своя выборка (`compute_period_stats`)."""
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


def _dynamics_whole_scope(
    db: Session,
    date_from: datetime.date,
    date_to: datetime.date,
    department_id: int | None,
    course: int | None,
) -> list[dict]:
    """Динамика по колледжу/отделению/курсу (без конкретной группы и студента) — те же
    числа, что даёт `_dynamics_per_day`, но студенты, членство, сдачи и отметки грузятся
    один раз на весь период, а не заново на каждый день (при 4000+ студентов это было
    самым медленным экраном)."""
    study_days = calendar_service.study_days_between(db, date_from, date_to, study_group_id=None, course=course)
    if not study_days:
        return []

    def scoped(stmt):
        stmt = stmt.join(StudyGroup, StudyGroup.id == Student.study_group_id)
        if course is not None:
            stmt = stmt.where(StudyGroup.course == course)
        if department_id is not None:
            stmt = stmt.where(StudyGroup.department_id == department_id)
        return stmt

    students = db.execute(
        scoped(select(Student.id, Student.enrolled_at, Student.left_at, Student.study_group_id))
    ).all()
    if not students:
        return [{"date": d, "percent": None, "in_list": None, "present": None} for d in study_days]

    memberships: dict[int, list[tuple[datetime.date, datetime.date | None, int]]] = defaultdict(list)
    for row in db.execute(
        scoped(
            select(
                StudentGroupMembership.student_id, StudentGroupMembership.start_date,
                StudentGroupMembership.end_date, StudentGroupMembership.study_group_id,
            ).join(Student, Student.id == StudentGroupMembership.student_id)
        )
    ).all():
        memberships[row.student_id].append((row.start_date, row.end_date, row.study_group_id))

    submitted = {
        (r.study_group_id, r.date)
        for r in db.execute(
            select(DaySubmission.study_group_id, DaySubmission.date).where(DaySubmission.date.in_(study_days))
        ).all()
    }

    marks_by_day: dict[datetime.date, list[tuple[int, bool]]] = defaultdict(list)  # (student_id, считается ли присутствием)
    for row in db.execute(
        scoped(
            select(AttendanceMark.student_id, AttendanceMark.date, MarkCode.counts_as_present)
            .join(Student, Student.id == AttendanceMark.student_id)
            .join(MarkCode, MarkCode.id == AttendanceMark.mark_code_id)
        ).where(AttendanceMark.date.in_(study_days))
    ).all():
        marks_by_day[row.date].append((row.student_id, row.counts_as_present))

    fk_group = {s.id: s.study_group_id for s in students}

    def group_on(student_id: int, day: datetime.date) -> int:
        for start, end, group_id in memberships.get(student_id, ()):
            if start <= day and (end is None or end >= day):
                return group_id
        return fk_group[student_id]

    result = []
    for day in study_days:
        in_list = 0
        for student_id, enrolled_at, left_at, _ in students:
            if enrolled_at <= day and (left_at is None or left_at >= day) and (group_on(student_id, day), day) in submitted:
                in_list += 1
        if in_list == 0:
            result.append({"date": day, "percent": None, "in_list": None, "present": None})
            continue
        absent = sum(
            1 for student_id, counts_as_present in marks_by_day.get(day, ())
            if not counts_as_present and (group_on(student_id, day), day) in submitted
        )
        present = in_list - absent
        result.append({"date": day, "percent": round(present / in_list * 100, 2), "in_list": in_list, "present": present})
    return result


def dynamics(
    db: Session,
    date_from: datetime.date,
    date_to: datetime.date,
    department_id: int | None = None,
    course: int | None = None,
    study_group_id: int | None = None,
    student_id: int | None = None,
) -> list[dict]:
    if study_group_id is None and student_id is None:
        return _dynamics_whole_scope(db, date_from, date_to, department_id, course)
    return _dynamics_per_day(db, date_from, date_to, department_id, course, study_group_id, student_id)


def curator_discipline(
    db: Session,
    date_from: datetime.date,
    date_to: datetime.date,
    department_id: int | None = None,
) -> list[dict]:
    groups = _active_groups(db, department_id)
    study_days_by_group = calendar_service.study_days_by_group(db, date_from, date_to, groups)

    by_group_date: dict[int, dict[datetime.date, DaySubmission]] = defaultdict(dict)
    if groups:
        for submission in db.execute(
            select(DaySubmission).where(
                DaySubmission.study_group_id.in_([g.id for g in groups]),
                DaySubmission.date >= date_from,
                DaySubmission.date <= date_to,
            )
        ).scalars().all():
            by_group_date[submission.study_group_id][submission.date] = submission

    rows = []
    for group in groups:
        study_days = study_days_by_group[group.id]
        by_date = by_group_date.get(group.id, {})
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


def curator_discipline_days(
    db: Session,
    group: StudyGroup,
    date_from: datetime.date,
    date_to: datetime.date,
) -> dict:
    """Дисциплина по одной группе день за днём: сдан ли день, когда (местное
    время колледжа) и кем. `submitted_at` в БД — время ПОСЛЕДНЕЙ сдачи: при
    пересдаче дня оно обновляется."""
    study_days = calendar_service.study_days_between(
        db, date_from, date_to, study_group_id=group.id, course=group.course
    )
    submissions = {}
    if study_days:
        submissions = {
            s.date: s
            for s in db.execute(
                select(DaySubmission).where(
                    DaySubmission.study_group_id == group.id, DaySubmission.date.in_(study_days)
                )
            ).scalars().all()
        }

    days = []
    on_time_minutes: list[int] = []
    for day in study_days:
        submission = submissions.get(day)
        if submission is None:
            days.append(
                {
                    "date": day, "status": "missed", "submitted_at_local": None, "submitted_by": None,
                    "first_period": None, "days_late": None,
                }
            )
            continue
        local = utc_to_local(submission.submitted_at)
        if submission.is_on_time:
            on_time_minutes.append(local.hour * 60 + local.minute)
        days.append(
            {
                "date": day,
                "status": "on_time" if submission.is_on_time else "late",
                "submitted_at_local": local,
                "submitted_by": submission.submitted_by.full_name,
                "first_period": submission.first_period,
                "days_late": None if submission.is_on_time else max((local.date() - day).days, 0),
            }
        )

    average = None
    if on_time_minutes:
        mean = round(sum(on_time_minutes) / len(on_time_minutes))
        average = f"{mean // 60:02d}:{mean % 60:02d}"
    on_time = sum(1 for d in days if d["status"] == "on_time")
    late = sum(1 for d in days if d["status"] == "late")
    return {
        "study_group_id": group.id,
        "group_code": group.code,
        "responsible_name": _current_responsible_name(group, date_to),
        "date_from": date_from,
        "date_to": date_to,
        "on_time": on_time,
        "late": late,
        "missed": len(days) - on_time - late,
        "total_study_days": len(days),
        "average_on_time_submission": average,
        "days": days,
    }


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
