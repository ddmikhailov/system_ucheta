"""Журнал индивидуальной работы (этап 5а): беседы, вызовы родителей, Совет профилактики,
визиты — это заметки досье особых видов, а здесь они сведены в обзор по группе.

  * «Группа внимания» — студенты, у которых серия неуважительных пропусков дошла до порога, и те,
    с кем уже ведётся работа (есть записи или открытые «вернуться к вопросу»);
  * «Нужна работа» — серия пропусков есть, а записи об индивидуальной работе за последние
    NO_WORK_DAYS дней нет;
  * «Вернуться к вопросу» — дата в заметке; когда она наступает, автору приходит напоминание."""
import datetime
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Student, StudentNote, User
from app.services import attendance_service, in_app_notification_service
from app.services.audit_service import log_action

WORK_KINDS = ("conversation", "call", "parent_invited", "prevention_council", "home_visit", "agreement")
NO_WORK_DAYS = 14


@dataclass
class WorkRow:
    student_id: int
    full_name: str
    risk_streak: int
    is_risk: bool
    work_count: int
    last_work_on: datetime.date | None
    next_follow_up_on: datetime.date | None
    follow_up_overdue: bool
    needs_attention: bool


def note_date(note: StudentNote) -> datetime.date:
    return note.occurred_on or note.created_at.date()


def group_overview(db: Session, group_id: int, today: datetime.date) -> list[WorkRow]:
    students = attendance_service.get_active_students(db, group_id, today)
    if not students:
        return []
    ids = [s.id for s in students]
    streaks = attendance_service.consecutive_unexcused_counts_bulk(db, students, today)
    threshold = get_settings().risk_threshold_consecutive_unexcused
    notes: dict[int, list[StudentNote]] = {}
    for n in db.query(StudentNote).filter(StudentNote.student_id.in_(ids), StudentNote.kind.in_(WORK_KINDS)):
        notes.setdefault(n.student_id, []).append(n)

    rows: list[WorkRow] = []
    for s in students:
        mine = notes.get(s.id, [])
        streak = streaks.get(s.id, 0)
        is_risk = streak >= threshold
        open_follow = sorted(n.follow_up_on for n in mine if n.follow_up_on and not n.follow_up_done)
        if not (is_risk or mine):
            continue
        last = max((note_date(n) for n in mine), default=None)
        recent = last is not None and (today - last).days <= NO_WORK_DAYS
        rows.append(WorkRow(
            student_id=s.id, full_name=s.full_name, risk_streak=streak, is_risk=is_risk, work_count=len(mine),
            last_work_on=last, next_follow_up_on=open_follow[0] if open_follow else None,
            follow_up_overdue=bool(open_follow and open_follow[0] < today),
            needs_attention=is_risk and not recent,
        ))
    rows.sort(key=lambda r: (not r.needs_attention, not r.follow_up_overdue, -r.risk_streak, r.full_name))
    return rows


def generate_followup_reminders(db: Session, user: User, today: datetime.date) -> int:
    """Автору заметки — напоминание, когда наступил срок «вернуться к вопросу». Одно на (студент, дата)."""
    due = (
        db.query(StudentNote, Student).join(Student, Student.id == StudentNote.student_id)
        .filter(StudentNote.author_id == user.id, StudentNote.follow_up_done.is_(False),
                StudentNote.follow_up_on.isnot(None), StudentNote.follow_up_on <= today)
        .all()
    )
    if not due:
        return 0
    from app.models import InAppNotification

    sent = {
        (n.entity_id, n.message)
        for n in db.query(InAppNotification.entity_id, InAppNotification.message).filter(
            InAppNotification.user_id == user.id, InAppNotification.kind == "work_followup")
    }
    created = 0
    for note, student in due:
        message = f"Пора вернуться к вопросу: {student.full_name} (срок {note.follow_up_on.strftime('%d.%m.%Y')})."
        key = (str(student.id), message)
        if key in sent:
            continue
        sent.add(key)
        in_app_notification_service.notify(db, user, "work_followup", message,
                                           entity_type="student", entity_id=str(student.id))
        created += 1
    return created


def set_follow_up_done(db: Session, user: User, note: StudentNote, done: bool) -> None:
    if note.follow_up_on is None:
        raise ValueError("В заметке нет даты возврата к вопросу")
    note.follow_up_done = done
    log_action(db, user, "dossier.follow_up_done" if done else "dossier.follow_up_reopen", "student", str(note.student_id),
               new_value=str(note.id))
