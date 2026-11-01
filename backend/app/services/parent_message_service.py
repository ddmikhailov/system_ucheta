"""Готовые тексты родителям (опоздания, длительное отсутствие, собрание, итог семестра): платформа подставляет данные,
куратор правит текст и копирует его в мессенджер (отправки из платформы нет: решение 30.09.2026). Пропуски без
уважительной причины — отдельный текст в `my_day_service.absence_message`, здесь он только подключается к общему виду.
Посещаемость и успеваемость идут отдельно: в тексте «итог семестра» только посещаемость."""
import datetime

from sqlalchemy.orm import Session

from app.core.time import today_local
from app.models import AbsencePeriod, ParentMeeting, Student, StudentProfile, User
from app.schemas.my_day import ParentMessage
from app.services import absence_sheet_service, curator_report_service, my_day_service, stats_service

KINDS = ("absences", "late", "long_absence", "meeting", "semester")
MAX_DAYS = 60
LONG_ABSENCE_LOOKBACK_DAYS = 60
MEETING_FORMATS = {"in_person": "очно", "remote": "дистанционно"}


def _fmt(d: datetime.date) -> str:
    return d.strftime("%d.%m.%Y")


def _who(db: Session, student: Student) -> str:
    profile = db.get(StudentProfile, student.id)
    return "студентки" if profile is not None and profile.gender == "female" else "студента"


def _intro(db: Session, student: Student) -> str:
    return (f"Здравствуйте! Пишу вам как куратор группы {student.study_group.code} о {_who(db, student)}: "
            f"{student.full_name}.")


def _sign(user: User) -> str:
    return f"С уважением, {user.full_name}."


def _empty(kind: str, reason: str) -> ParentMessage:
    return ParentMessage(kind=kind, text="", empty_reason=reason)


def _late(db: Session, student: Student, user: User, days: int, today: datetime.date) -> ParentMessage:
    start = today - datetime.timedelta(days=days - 1)
    lates = [r for r in absence_sheet_service.collect_rows(db, student, start, today) if r.is_late]
    if not lates:
        return _empty("late", f"За последние {days} дн. нет опозданий — сообщать нечего.")
    lines = "\n".join(f"• {_fmt(r.date)}" for r in lates)
    text = (f"{_intro(db, student)} За последние {days} дн. студент опаздывал на занятия:\n{lines}\n"
            "Прошу поговорить с ним и сообщить, если есть причина, о которой стоит знать.\n"
            f"{_sign(user)}")
    return ParentMessage(kind="late", text=text)


def _long_absence(db: Session, student: Student, user: User, today: datetime.date) -> ParentMessage:
    since = today - datetime.timedelta(days=LONG_ABSENCE_LOOKBACK_DAYS)
    period = (
        db.query(AbsencePeriod)
        .filter(AbsencePeriod.student_id == student.id, AbsencePeriod.date_to >= since)
        .order_by(AbsencePeriod.date_from.desc())
        .first()
    )
    if period is None:
        return _empty("long_absence", "У студента нет длительного отсутствия за последние 60 дней — сообщать нечего.")
    basis = f" Основание: {period.basis_reference}." if period.basis_reference else ""
    ends = "продолжается" if period.date_to >= today else "закончилось"
    text = (f"{_intro(db, student)} В журнале указано длительное отсутствие с {_fmt(period.date_from)} "
            f"по {_fmt(period.date_to)} ({period.mark_code.name}); оно {ends}.{basis}\n"
            "Прошу сообщить, когда студент вернётся на занятия, и принести подтверждающий документ, если его ещё нет.\n"
            f"{_sign(user)}")
    return ParentMessage(kind="long_absence", text=text)


def _meeting(db: Session, student: Student, user: User, today: datetime.date) -> ParentMessage:
    meeting = (
        db.query(ParentMeeting)
        .filter(ParentMeeting.study_group_id == student.study_group_id, ParentMeeting.meeting_date >= today)
        .order_by(ParentMeeting.meeting_date)
        .first()
    )
    if meeting is None:
        return _empty("meeting", "У группы нет запланированного родительского собрания. Создайте собрание в разделе «Собрания».")
    agenda = [a.strip() for a in (meeting.agenda or "").splitlines() if a.strip()]
    agenda_text = ("Вопросы собрания:\n" + "\n".join(f"• {a}" for a in agenda) + "\n") if agenda else ""
    fmt = MEETING_FORMATS.get(meeting.meeting_format, "очно")
    text = (f"Здравствуйте! Приглашаю вас на родительское собрание группы {student.study_group.code}. "
            f"Дата: {_fmt(meeting.meeting_date)}. Формат: {fmt}.\n{agenda_text}"
            "Ваше участие важно. Прошу подтвердить, что вы придёте.\n"
            f"{_sign(user)}")
    return ParentMessage(kind="meeting", text=text)


def _semester(db: Session, student: Student, user: User, today: datetime.date) -> ParentMessage:
    semester = curator_report_service.current_semester(today)
    year_start = today.year if today.month >= 9 else today.year - 1
    start, _ = curator_report_service.period(f"{year_start}-{year_start + 1}", semester)
    stats = stats_service.compute_period_stats(db, start, today, student_id=student.id, only_submitted=True)
    if stats.in_list == 0:
        return _empty("semester", "В этом семестре нет сданных дней — итог посещаемости посчитать нечего.")
    text = (f"{_intro(db, student)} Итог посещаемости за {semester}-й семестр (с {_fmt(start)} по {_fmt(today)}):\n"
            f"• посещаемость — {stats.percent:g}%;\n"
            f"• пропусков по уважительной причине — {stats.absent_excused};\n"
            f"• пропусков без уважительной причины — {stats.absent_unexcused};\n"
            f"• опозданий — {stats.late}.\n"
            "Прошу обратить внимание на посещаемость и при необходимости связаться со мной.\n"
            f"{_sign(user)}")
    return ParentMessage(kind="semester", text=text)


def build(db: Session, student: Student, user: User, kind: str, days: int, today: datetime.date | None = None) -> ParentMessage:
    today = today or today_local()
    days = min(max(days, 1), MAX_DAYS)
    if kind == "absences":
        m = my_day_service.absence_message(db, student, user, days, today)
        reason = f"За последние {m.days} дн. нет пропусков без уважительной причины — сообщать нечего." if not m.text else None
        return ParentMessage(kind=kind, text=m.text, empty_reason=reason)
    if kind == "late":
        return _late(db, student, user, days, today)
    if kind == "long_absence":
        return _long_absence(db, student, user, today)
    if kind == "meeting":
        return _meeting(db, student, user, today)
    return _semester(db, student, user, today)
