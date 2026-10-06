"""«Мой день» (этап 6): одна страница куратора — что требует внимания сегодня.

Только агрегация уже существующих данных, новых таблиц нет:
  * группы — сдан ли сегодняшний день и какие учебные дни за последние недели остались несданными;
  * задачи — просроченные, возвращённые на доработку и со сроком в ближайшие дни;
  * внимание — студенты из журнала индивидуальной работы (серия пропусков без работы, срок «вернуться
    к вопросу» сегодня или просрочен);
  * дни рождения студентов своих групп на неделю вперёд;
  * для проверяющих по задачам — сколько назначений ждёт их решения.
Особые данные досье сюда не попадают: список виден тем же людям, что и журнал групп, а особые поля — уже."""
import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.time import today_local
from app.models import (
    AttendanceMark, CuratorAssignment, DaySubmission, MarkCode, RoleCode, Student, StudentProfile, StudyGroup,
    TaskAssignment, User,
)
from app.schemas.my_day import (
    AbsenceLine, AbsenceMessage, AttentionStudent, Birthday, DayGroup, DayTask, MyDay, ReviewWaiting, RhythmDay,
)
from app.services import attendance_service, calendar_service, individual_work_service
from app.services import task_service
from app.services.access_service import get_curator_group_ids

DUE_SOON_DAYS = 3
BIRTHDAY_DAYS = 7
MISSED_LOOKBACK_DAYS = 14
MAX_MISSED_DATES = 5
RHYTHM_DAYS = 21
MAX_ATTENTION = 30
MAX_ABSENCE_DAYS = 60

_TASK_KIND_ORDER = {"overdue": 0, "returned": 1, "due_soon": 2}


def _my_groups(db: Session, user: User, today: datetime.date) -> list[StudyGroup]:
    ids = get_curator_group_ids(db, user, today)
    if not ids:
        return []
    return db.query(StudyGroup).filter(StudyGroup.id.in_(ids)).order_by(StudyGroup.course, StudyGroup.code).all()


def _unexcused_by_day(db: Session, group_ids: list[int], start: datetime.date, end: datetime.date) -> dict[tuple[int, datetime.date], int]:
    """Сколько пропусков без уважительной причины в каждой группе по дням — одним запросом."""
    rows = (
        db.query(Student.study_group_id, AttendanceMark.date, func.count(AttendanceMark.id))
        .join(Student, Student.id == AttendanceMark.student_id)
        .join(MarkCode, MarkCode.id == AttendanceMark.mark_code_id)
        .filter(Student.study_group_id.in_(group_ids), AttendanceMark.date >= start, AttendanceMark.date <= end,
                MarkCode.counts_as_present.is_(False), MarkCode.is_excused.is_(False))
        .group_by(Student.study_group_id, AttendanceMark.date)
        .all()
    )
    return {(group_id, day): count for group_id, day, count in rows}


def group_rhythm(
    db: Session, group: StudyGroup, today: datetime.date, submitted: set[datetime.date],
    unexcused: dict[tuple[int, datetime.date], int], study_days: set[datetime.date] | None = None,
) -> list[RhythmDay]:
    start = today - datetime.timedelta(days=RHYTHM_DAYS - 1)
    if study_days is None:
        study_days = set(calendar_service.study_days_between(db, start, today, study_group_id=group.id, course=group.course))
    result: list[RhythmDay] = []
    for i in range(RHYTHM_DAYS):
        day = start + datetime.timedelta(days=i)
        if day not in study_days:
            result.append(RhythmDay(date=day, kind="off"))
        elif day not in submitted:
            result.append(RhythmDay(date=day, kind="missing"))
        else:
            absent = unexcused.get((group.id, day), 0)
            result.append(RhythmDay(date=day, kind="absent" if absent else "ok", absent=absent))
    return result


def rhythm_for_group(db: Session, group: StudyGroup, today: datetime.date | None = None) -> list[RhythmDay]:
    """«Ритм группы» отдельно — для журнала группы (кабинет куратора, журнал в админке)."""
    today = today or today_local()
    start = today - datetime.timedelta(days=RHYTHM_DAYS - 1)
    submitted = {
        d for (d,) in db.query(DaySubmission.date).filter(
            DaySubmission.study_group_id == group.id, DaySubmission.date >= start, DaySubmission.date <= today)
    }
    return group_rhythm(db, group, today, submitted, _unexcused_by_day(db, [group.id], start, today))


def day_groups(db: Session, user: User, groups: list[StudyGroup], today: datetime.date) -> list[DayGroup]:
    if not groups:
        return []
    window_start = today - datetime.timedelta(days=max(MISSED_LOOKBACK_DAYS, RHYTHM_DAYS))
    unexcused = _unexcused_by_day(db, [g.id for g in groups], window_start, today)
    submissions: dict[tuple[int, datetime.date], DaySubmission] = {
        (s.study_group_id, s.date): s
        for s in db.query(DaySubmission).filter(
            DaySubmission.study_group_id.in_([g.id for g in groups]),
            DaySubmission.date >= window_start, DaySubmission.date <= today)
    }
    # Календарь всех групп и назначения пользователя — разом, а не по запросу на группу.
    calendar = calendar_service.study_days_by_group(db, window_start, today, groups)
    starts: dict[int, datetime.date] = {}
    for a in db.query(CuratorAssignment).filter(
        CuratorAssignment.user_id == user.id, CuratorAssignment.study_group_id.in_([g.id for g in groups])
    ):
        if a.is_active_on(today):
            starts[a.study_group_id] = min(a.start_date, starts.get(a.study_group_id, a.start_date))
    rhythm_start = today - datetime.timedelta(days=RHYTHM_DAYS - 1)
    result: list[DayGroup] = []
    for g in groups:
        missed_start = today - datetime.timedelta(days=MISSED_LOOKBACK_DAYS)
        start = max(missed_start, starts.get(g.id) or missed_start)
        study_days = [d for d in calendar[g.id] if d >= start]
        today_sub = submissions.get((g.id, today))
        if today not in study_days:
            today_status = "no_study_day"
        else:
            today_status = "submitted" if today_sub is not None else "pending"
        missed = sorted(
            (d for d in study_days if d < today and (g.id, d) not in submissions), reverse=True)
        submitted_days = {d for (gid, d) in submissions if gid == g.id}
        result.append(DayGroup(
            id=g.id, code=g.code, course=g.course, today_status=today_status,
            is_on_time=today_sub.is_on_time if today_sub is not None else None,
            missed_dates=missed[:MAX_MISSED_DATES], missed_total=len(missed),
            rhythm=group_rhythm(
                db, g, today, submitted_days, unexcused, study_days={d for d in calendar[g.id] if d >= rhythm_start}),
        ))
    return result


def day_tasks(db: Session, groups: list[StudyGroup], today: datetime.date) -> list[DayTask]:
    if not groups:
        return []
    rows = (
        db.query(TaskAssignment)
        .options(joinedload(TaskAssignment.task), joinedload(TaskAssignment.study_group))
        .filter(TaskAssignment.study_group_id.in_([g.id for g in groups]), TaskAssignment.status != "accepted",
                TaskAssignment.locked.is_(False))
        .all()
    )
    tasks: list[DayTask] = []
    for a in rows:
        task = a.task
        # «Отправлено» — ход проверяющего; закрытая задача и закрытый шаг цепочки куратора не касаются.
        if task.is_closed or a.status == "submitted":
            continue
        days_left = (task.due_date - today).days
        if days_left < 0:
            kind = "overdue"
        elif a.status == "returned":
            kind = "returned"
        elif days_left <= DUE_SOON_DAYS:
            kind = "due_soon"
        else:
            continue
        tasks.append(DayTask(
            assignment_id=a.id, title=task.title, group_code=a.study_group.code, due_date=task.due_date,
            kind=kind, status=a.status, days_left=days_left,
        ))
    tasks.sort(key=lambda t: (_TASK_KIND_ORDER[t.kind], t.due_date, t.assignment_id))
    return tasks


def day_attention(db: Session, groups: list[StudyGroup], today: datetime.date) -> tuple[list[AttentionStudent], int]:
    items: list[AttentionStudent] = []
    for g in groups:
        for r in individual_work_service.group_overview(db, g.id, today):
            follow_today = r.next_follow_up_on == today
            if not (r.needs_attention or r.follow_up_overdue or follow_today):
                continue
            items.append(AttentionStudent(
                student_id=r.student_id, full_name=r.full_name, group_code=g.code, risk_streak=r.risk_streak,
                attendance_percent=r.attendance_percent,
                needs_work=r.needs_attention, last_work_on=r.last_work_on, follow_up_on=r.next_follow_up_on,
                follow_up_overdue=r.follow_up_overdue, follow_up_today=follow_today,
            ))
    items.sort(key=lambda s: (not s.needs_work, not s.follow_up_overdue, not s.follow_up_today,
                              s.attendance_percent if s.attendance_percent is not None else 101.0, s.full_name))
    return items[:MAX_ATTENTION], len(items)


def next_birthday(born: datetime.date, today: datetime.date) -> datetime.date:
    """Ближайший день рождения не раньше сегодняшнего; 29 февраля в невисокосный год отмечаем 28-го."""
    for year in (today.year, today.year + 1):
        try:
            candidate = born.replace(year=year)
        except ValueError:
            candidate = datetime.date(year, 2, 28)
        if candidate >= today:
            return candidate
    return born.replace(year=today.year + 1)  # недостижимо: хватает двух лет


def day_birthdays(db: Session, groups: list[StudyGroup], today: datetime.date) -> list[Birthday]:
    students: list[tuple[Student, StudyGroup]] = []
    for g in groups:
        students.extend((s, g) for s in attendance_service.get_active_students(db, g.id, today))
    if not students:
        return []
    born = {
        p.student_id: p.birth_date
        for p in db.query(StudentProfile).filter(
            StudentProfile.student_id.in_([s.id for s, _ in students]), StudentProfile.birth_date.isnot(None))
    }
    result: list[Birthday] = []
    for s, g in students:
        b = born.get(s.id)
        if b is None:
            continue
        nxt = next_birthday(b, today)
        days_until = (nxt - today).days
        if days_until > BIRTHDAY_DAYS:
            continue
        result.append(Birthday(student_id=s.id, full_name=s.full_name, group_code=g.code, date=nxt,
                               days_until=days_until, turns=nxt.year - b.year))
    result.sort(key=lambda x: (x.days_until, x.full_name))
    return result


def review_waiting(db: Session, user: User) -> ReviewWaiting | None:
    """Сколько назначений ждёт решения этого пользователя — только для ролей, которые проверяют задачи."""
    if not task_service.is_manager(user):
        return None
    mine = [
        a for a in db.query(TaskAssignment).filter(TaskAssignment.status == "submitted")
        .options(joinedload(TaskAssignment.task), joinedload(TaskAssignment.study_group))
        if task_service.can_review(user, a)
    ]
    submitted = [a.submitted_at for a in mine if a.submitted_at is not None]
    return ReviewWaiting(count=len(mine), oldest_submitted_at=min(submitted) if submitted else None)


def build_my_day(db: Session, user: User, today: datetime.date | None = None) -> MyDay:
    today = today or today_local()
    groups = _my_groups(db, user, today)
    attention, attention_total = day_attention(db, groups, today)
    return MyDay(
        today=today, leads_groups=bool(groups), groups=day_groups(db, user, groups, today),
        tasks=day_tasks(db, groups, today), attention=attention, attention_total=attention_total,
        no_work_days=individual_work_service.NO_WORK_DAYS, birthdays=day_birthdays(db, groups, today), review_waiting=review_waiting(db, user),
    )


def nav_counters(db: Session, user: User, today: datetime.date | None = None) -> dict[str, int]:
    """Числа на пунктах меню: дела на сегодня («Мой день»), горящие задачи куратора, ответы на проверке.
    Только подсчёт по уже имеющимся данным, без досье и без посещаемости по студентам."""
    today = today or today_local()
    groups = _my_groups(db, user, today)
    tasks = len(day_tasks(db, groups, today))
    pending_days = 0
    if groups:
        submitted = {
            s.study_group_id for s in db.query(DaySubmission).filter(
                DaySubmission.study_group_id.in_([g.id for g in groups]), DaySubmission.date == today)
        }
        calendar = calendar_service.study_days_by_group(db, today, today, groups)
        pending_days = sum(1 for g in groups if g.id not in submitted and today in calendar[g.id])
    return {"my_day": pending_days + tasks, "my_tasks": tasks, "review": review_count(db, user)}


def review_count(db: Session, user: User) -> int:
    """Сколько ответов ждут решения пользователя. Администратор проверяет всё — ему хватает COUNT; остальным
    правило проверки (ступень, отделение, автор) применяется к каждому назначению, как в очереди."""
    if not task_service.is_manager(user):
        return 0
    if RoleCode(user.role.code) == RoleCode.ADMIN:
        return db.query(TaskAssignment).filter(TaskAssignment.status == "submitted").count()
    waiting = review_waiting(db, user)
    return waiting.count if waiting else 0


# ---------- быстрые действия ----------

def _fmt(d: datetime.date) -> str:
    return d.strftime("%d.%m.%Y")


def absence_message(db: Session, student: Student, user: User, days: int, today: datetime.date | None = None) -> AbsenceMessage:
    """Готовый текст родителям о пропусках без уважительной причины за последние `days` дней — куратор
    копирует его в мессенджер (отправки из платформы нет: решение 30.09.2026). В текст попадают только отметки
    «не присутствовал и причина не уважительная» («н», «у»): больничный, приказ, практика родителям
    «разъяснять» не нужно — причина известна."""
    today = today or today_local()
    days = min(max(days, 1), MAX_ABSENCE_DAYS)
    start = today - datetime.timedelta(days=days - 1)
    rows = (
        db.query(AttendanceMark.date, MarkCode.code, MarkCode.name)
        .join(MarkCode, MarkCode.id == AttendanceMark.mark_code_id)
        .filter(AttendanceMark.student_id == student.id, AttendanceMark.date >= start,
                AttendanceMark.date <= today, MarkCode.counts_as_present.is_(False), MarkCode.is_excused.is_(False))
        .order_by(AttendanceMark.date)
    )
    absences = [AbsenceLine(date=r.date, code=r.code, name=r.name) for r in rows]
    if not absences:
        return AbsenceMessage(days=days, absences=[], text="")
    lines = "\n".join(f"• {_fmt(a.date)} — {a.name}" for a in absences)
    profile = db.get(StudentProfile, student.id)
    who = "студентки" if profile is not None and profile.gender == "female" else "студента"
    text = (
        f"Здравствуйте! Пишу вам как куратор группы {student.study_group.code} о посещаемости {who}: "
        f"{student.full_name}. За последние {days} дн. в журнале нет отметки об уважительной причине:\n{lines}\n"
        "Прошу сообщить причину отсутствия.\n"
        f"С уважением, {user.full_name}."
    )
    return AbsenceMessage(days=days, absences=absences, text=text)
