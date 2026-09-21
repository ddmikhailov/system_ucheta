"""Тексты сообщений бота — все на русском, по формулировкам из концепции."""
import datetime

from app.services.notification_service import CollegeSummary, DeptHeadDigestRow, LeadershipDigest


def _fmt_date(date: datetime.date) -> str:
    return date.strftime("%d.%m.%Y")


def start_welcome_no_payload() -> str:
    return (
        "Это бот платформы учёта посещаемости КАИТ-20.\n\n"
        "Подключить уведомления можно только из личного кабинета на сайте: "
        "кнопка «Подключить Telegram» выдаст одноразовую ссылку. "
        "Сам бот написать вам первым не может, пока вы не перешли по ней."
    )


def link_success(full_name: str) -> str:
    return f"Готово, {full_name}! Уведомления будут приходить сюда."


def link_invalid() -> str:
    return "Ссылка недействительна или уже использована. Получите новую в личном кабинете."


def link_chat_taken() -> str:
    return "Этот Telegram уже привязан к другой учётной записи на платформе."


def reminder_message(group_codes: list[str], is_second: bool) -> str:
    groups_line = ", ".join(group_codes)
    if is_second:
        header = "Повторное напоминание: день ещё не сдан"
    else:
        header = "Не забудьте отметить посещаемость"
    return f"{header}\n\nГруппы: {groups_line}\n\nВыберите группу ниже."


def submit_confirmed(group_code: str, date: datetime.date) -> str:
    return f"Готово — {group_code}, {_fmt_date(date)}: все присутствуют. День сдан."


def submit_backdate_denied(reason: str) -> str:
    return f"Не получилось: {reason}"


def dept_head_digest(rows: list[DeptHeadDigestRow], department_name: str, date: datetime.date) -> str:
    if not rows:
        return f"«{department_name}», {_fmt_date(date)}: все группы сдали день. 👍"
    lines = [f"Несданные группы отделения «{department_name}» на {_fmt_date(date)}:"]
    for row in rows:
        curator = row.responsible_name or "нет куратора"
        lines.append(f"— {row.group_code}: {curator}")
    return "\n".join(lines)


def edu_department_digest(summary: CollegeSummary, date: datetime.date) -> str:
    lines = [
        f"Сводка по колледжу на {_fmt_date(date)}:",
        f"Сдано {summary.submitted_groups} из {summary.total_groups}",
        f"Присутствие: {summary.percent}%",
    ]
    if summary.problem_groups:
        lines.append("Проблемные группы: " + ", ".join(summary.problem_groups))
    return "\n".join(lines)


def leadership_digest(digest: LeadershipDigest) -> str:
    period = f"{digest.date_from.strftime('%d.%m')} – {digest.date_to.strftime('%d.%m.%Y')}"
    return (
        f"Недельный дайджест ({period})\n\n"
        f"Присутствие по колледжу: {digest.college_percent}%\n"
        f"Сдача дня: вовремя — {digest.on_time_total}, с опозданием — {digest.late_total}, "
        f"не сдано — {digest.missed_total}\n"
        f"Студентов в группе риска: {digest.risk_students_count}"
    )
