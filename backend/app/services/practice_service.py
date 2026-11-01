"""Практика группы (п. 3.1.17 положения о кураторе): период практики, база, руководители, факт получения
характеристики. Период ставит всем студентам группы отметку практики («р») на учебные дни — через длительные периоды
отсутствия (`AbsencePeriod.group_practice_id`), поэтому журнал, процент посещаемости и «Восполнить пропуски»
работают как для обычного периода: «р» — отсутствие, но восполнять его не нужно (флаг кода `no_compensation`)."""
import datetime
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AbsencePeriod, AttendanceMark, GroupPractice, MarkCode, Student, StudyGroup, User
from app.services import attendance_service, group_membership_service
from app.services.audit_service import log_action

PRACTICE_CODE = "р"
KINDS = {"educational": "Учебная", "production": "Производственная", "pre_diploma": "Преддипломная"}
MAX_DAYS = 366
SOON_DAYS = 14  # «скоро начнётся» в сводке
OVERDUE_DAYS = 180  # как давно закончившаяся практика без характеристики ещё показывается в сводке


class PracticeError(Exception):
    """Нельзя сохранить практику: текст показывается пользователю."""


def practice_code(db: Session) -> MarkCode:
    code = db.execute(select(MarkCode).where(MarkCode.code == PRACTICE_CODE)).scalar_one_or_none()
    if code is None:
        raise PracticeError("В справочнике нет кода практики «р»")
    return code


def validate_dates(date_from: datetime.date, date_to: datetime.date) -> None:
    if date_to < date_from:
        raise PracticeError("Дата окончания раньше даты начала")
    if (date_to - date_from).days > MAX_DAYS:
        raise PracticeError("Практика не может быть длиннее года")


def _students_in_period(db: Session, group_id: int, date_from: datetime.date, date_to: datetime.date) -> list[Student]:
    ids = group_membership_service.students_ever_in_group(db, group_id, date_from, date_to)
    if not ids:
        return []
    return [
        s for s in db.execute(select(Student).where(Student.id.in_(ids)).order_by(Student.id)).scalars()
        if s.enrolled_at <= date_to and (s.left_at is None or s.left_at >= date_from)
    ]


def _new_period(practice: GroupPractice, student: Student, code: MarkCode) -> AbsencePeriod:
    return AbsencePeriod(
        student_id=student.id, mark_code_id=code.id, group_practice_id=practice.id,
        date_from=max(practice.date_from, student.enrolled_at),
        date_to=min(practice.date_to, student.left_at) if student.left_at else practice.date_to,
        created_by_user_id=practice.created_by_user_id,
    )


def count_replaced_marks(db: Session, group_id: int, date_from: datetime.date, date_to: datetime.date) -> int:
    """Сколько уже поставленных отметок (не практики) перезапишет практика — для предупреждения куратору."""
    ids = group_membership_service.students_ever_in_group(db, group_id, date_from, date_to)
    if not ids:
        return 0
    q = (
        select(AttendanceMark.id)
        .join(MarkCode, MarkCode.id == AttendanceMark.mark_code_id)
        .where(AttendanceMark.student_id.in_(ids), AttendanceMark.date >= date_from, AttendanceMark.date <= date_to,
               MarkCode.code != PRACTICE_CODE)
    )
    return len(db.execute(q).all())


def sync(db: Session, practice: GroupPractice, user: User) -> None:
    """Пересоздать отметки практики: прежние периоды снимаются, всем студентам группы ставятся заново. Без commit."""
    code = practice_code(db)
    old = db.execute(select(AbsencePeriod).where(AbsencePeriod.group_practice_id == practice.id)).scalars().all()
    for period in old:
        attendance_service._drop_period_marks(db, period, user)
        db.delete(period)
    db.flush()
    for student in _students_in_period(db, practice.study_group_id, practice.date_from, practice.date_to):
        period = _new_period(practice, student, code)
        if period.date_from > period.date_to:
            continue
        db.add(period)
        db.flush()
        attendance_service._apply_period_marks(db, period, code, user)


def remove(db: Session, practice: GroupPractice, user: User) -> None:
    """Убрать практику вместе с её отметками. Без commit."""
    for period in db.execute(select(AbsencePeriod).where(AbsencePeriod.group_practice_id == practice.id)).scalars():
        attendance_service._drop_period_marks(db, period, user)
        db.delete(period)
    db.flush()
    db.delete(practice)


def fill_missing(db: Session, group_id: int, date: datetime.date) -> None:
    """Студент пришёл в группу уже во время практики — ему тоже ставится «р». Вызывается при открытии журнала дня."""
    practices = db.execute(
        select(GroupPractice).where(
            GroupPractice.study_group_id == group_id, GroupPractice.date_from <= date, GroupPractice.date_to >= date,
            GroupPractice.created_by_user_id.is_not(None),
        )
    ).scalars().all()
    if not practices:
        return
    changed = False
    for practice in practices:
        have = set(db.execute(
            select(AbsencePeriod.student_id).where(AbsencePeriod.group_practice_id == practice.id)
        ).scalars())
        missing = [s for s in _students_in_period(db, group_id, practice.date_from, practice.date_to) if s.id not in have]
        if not missing:
            continue
        code = practice_code(db)
        user = db.get(User, practice.created_by_user_id)
        for student in missing:
            period = _new_period(practice, student, code)
            if period.date_from > period.date_to:
                continue
            db.add(period)
            db.flush()
            attendance_service._apply_period_marks(db, period, code, user)
            changed = True
    if changed:
        db.commit()


def audit(db: Session, user: User, action: str, practice: GroupPractice) -> None:
    log_action(db, user, action, "study_group", str(practice.study_group_id), new_value=str(practice.id))


@dataclass(frozen=True)
class CurrentPractice:
    practice: GroupPractice
    group: StudyGroup
    state: str  # active / soon / no_review


def state_of(practice: GroupPractice, today: datetime.date) -> str | None:
    if practice.date_from <= today <= practice.date_to:
        return "active"
    if today < practice.date_from <= today + datetime.timedelta(days=SOON_DAYS):
        return "soon"
    if practice.date_to < today <= practice.date_to + datetime.timedelta(days=OVERDUE_DAYS) and not practice.review_received:
        return "no_review"
    return None


def current(db: Session, department_id: int | None, today: datetime.date) -> list[CurrentPractice]:
    """Сводка для заведующего: какие группы сейчас на практике, какие скоро уйдут и по каким нет характеристики."""
    q = (
        select(GroupPractice, StudyGroup)
        .join(StudyGroup, StudyGroup.id == GroupPractice.study_group_id)
        .where(GroupPractice.date_to >= today - datetime.timedelta(days=OVERDUE_DAYS),
               GroupPractice.date_from <= today + datetime.timedelta(days=SOON_DAYS))
    )
    if department_id is not None:
        q = q.where(StudyGroup.department_id == department_id)
    order = {"active": 0, "no_review": 1, "soon": 2}
    rows = [CurrentPractice(p, g, st) for p, g in db.execute(q).all() if (st := state_of(p, today))]
    return sorted(rows, key=lambda r: (order[r.state], r.group.code, r.practice.date_from))
