"""Задания планировщика — расписание рассылок из концепции (раздел
«Telegram-бот»). Каждое задание идемпотентно: перед отправкой проверяет
notification_log, чтобы перезапуск процесса не задвоил сообщение.

Каждая функция принимает необязательный `today` — планировщик его не
передаёт (берётся текущая дата), а тесты фиксируют дату явно, не трогая
глобальный datetime.date.today()."""
import datetime
import logging

from aiogram import Bot

from app.db import base as db_base
from app.services import calendar_service, notification_service
from bot import keyboards, messages

logger = logging.getLogger(__name__)


async def _send(bot: Bot, chat_id: str, text: str, reply_markup=None) -> bool:
    try:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        return True
    except Exception:  # аккаунт мог отписаться от бота, чат мог стать недоступен и т.п.
        logger.exception("Не удалось отправить сообщение chat_id=%s", chat_id)
        return False


async def send_reminders(bot: Bot, kind: str, is_second: bool, today: datetime.date | None = None) -> None:
    today = today or datetime.date.today()
    db = db_base.SessionLocal()
    try:
        if not calendar_service.is_study_day(db, today):
            return

        by_user = notification_service.groups_needing_reminder(db, today)
        for user, groups in by_user.items():
            if notification_service.was_notified(db, user.id, kind, today):
                continue
            text = messages.reminder_message([g.code for g in groups], is_second)
            keyboard = keyboards.reminder_keyboard(groups, today)
            if await _send(bot, user.telegram_chat_id, text, keyboard):
                notification_service.record_notification(db, user.id, kind, today)
    finally:
        db.close()


async def send_first_reminder(bot: Bot, today: datetime.date | None = None) -> None:
    await send_reminders(bot, "reminder_1", is_second=False, today=today)


async def send_second_reminder(bot: Bot, today: datetime.date | None = None) -> None:
    await send_reminders(bot, "reminder_2", is_second=True, today=today)


async def send_dept_head_digest(bot: Bot, today: datetime.date | None = None) -> None:
    today = today or datetime.date.today()
    db = db_base.SessionLocal()
    try:
        if not calendar_service.is_study_day(db, today):
            return

        for user in notification_service.dept_heads_with_telegram(db):
            if notification_service.was_notified(db, user.id, "dept_head_digest", today):
                continue
            if user.department is None:
                continue
            rows = notification_service.dept_head_unsubmitted_groups(db, user.department, today)
            text = messages.dept_head_digest(rows, user.department.name, today)
            if await _send(bot, user.telegram_chat_id, text):
                notification_service.record_notification(db, user.id, "dept_head_digest", today)
    finally:
        db.close()


async def send_edu_department_digest(bot: Bot, today: datetime.date | None = None) -> None:
    today = today or datetime.date.today()
    db = db_base.SessionLocal()
    try:
        if not calendar_service.is_study_day(db, today):
            return

        summary = notification_service.college_day_summary(db, today)
        text = messages.edu_department_digest(summary, today)
        for user in notification_service.edu_department_recipients(db):
            if notification_service.was_notified(db, user.id, "edu_department_digest", today):
                continue
            if await _send(bot, user.telegram_chat_id, text):
                notification_service.record_notification(db, user.id, "edu_department_digest", today)
    finally:
        db.close()


async def send_leadership_digest(bot: Bot, today: datetime.date | None = None) -> None:
    today = today or datetime.date.today()
    db = db_base.SessionLocal()
    try:
        date_from = today - datetime.timedelta(days=6)
        digest = notification_service.leadership_weekly_digest(db, date_from, today)
        text = messages.leadership_digest(digest)
        for user in notification_service.leadership_recipients(db):
            if notification_service.was_notified(db, user.id, "leadership_digest", today):
                continue
            if await _send(bot, user.telegram_chat_id, text):
                notification_service.record_notification(db, user.id, "leadership_digest", today)
    finally:
        db.close()
