"""Задания планировщика — расписание рассылок из концепции (раздел
«Telegram-бот»). Каждое задание идемпотентно: перед отправкой проверяет
notification_log, чтобы перезапуск процесса не задвоил сообщение.

Каждая функция принимает необязательный `today` — планировщик его не
передаёт (берётся текущая дата), а тесты фиксируют дату явно, не трогая
глобальный datetime.date.today()."""
import asyncio
import datetime
import logging

from aiogram import Bot

from app.db import base as db_base
from app.services import notification_service
from bot import keyboards, messages

logger = logging.getLogger(__name__)


async def _send(bot: Bot, chat_id: str, text: str, reply_markup=None) -> bool:
    try:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        return True
    except Exception:  # аккаунт мог отписаться от бота, чат мог стать недоступен и т.п.
        logger.exception("Не удалось отправить сообщение chat_id=%s", chat_id)
        return False


def _groups_needing_reminder(today: datetime.date):
    # Синхронный поход в БД (сотни запросов на день по колледжу, см.
    # TODO.md 5) выполняется в отдельном потоке — во встроенном режиме
    # (EMBED_WORKERS=true) это тот же event loop, что обслуживает HTTP,
    # и без to_thread рассылка на время своего выполнения замораживала
    # бы весь сайт.
    db = db_base.SessionLocal()
    try:
        return notification_service.groups_needing_reminder(db, today)
    finally:
        db.close()


async def send_reminders(bot: Bot, kind: str, is_second: bool, today: datetime.date | None = None) -> None:
    today = today or datetime.date.today()
    # Раньше здесь была общая на весь колледж проверка "сегодня учебный
    # день?" — по субботам она либо слала напоминания всем (включая
    # курсы без занятий), либо не слала никому, включая 1 курс, у
    # которого по субботам как раз есть занятия (см. TODO.md 3).
    # groups_needing_reminder уже фильтрует по каждой группе отдельно.
    by_user = await asyncio.to_thread(_groups_needing_reminder, today)

    db = db_base.SessionLocal()
    try:
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


def _dept_head_payloads(today: datetime.date) -> list[tuple[int, str, str]]:
    # dept_head_unsubmitted_groups фильтрует по каждой группе отдельно (см.
    # пояснение в send_reminders выше) — тяжёлая часть, поэтому уходит целиком
    # в отдельный поток. Возвращаем только простые значения (id/chat_id/текст),
    # а не ORM-объекты: user.department — ленивая связь, и обращение к ней уже
    # после закрытия этой сессии упало бы с DetachedInstanceError.
    db = db_base.SessionLocal()
    try:
        payloads = []
        for user in notification_service.dept_heads_with_telegram(db):
            if notification_service.was_notified(db, user.id, "dept_head_digest", today):
                continue
            if user.department is None:
                continue
            rows = notification_service.dept_head_unsubmitted_groups(db, user.department, today)
            text = messages.dept_head_digest(rows, user.department.name, today)
            payloads.append((user.id, user.telegram_chat_id, text))
        return payloads
    finally:
        db.close()


async def send_dept_head_digest(bot: Bot, today: datetime.date | None = None) -> None:
    today = today or datetime.date.today()
    payloads = await asyncio.to_thread(_dept_head_payloads, today)

    db = db_base.SessionLocal()
    try:
        for user_id, chat_id, text in payloads:
            if await _send(bot, chat_id, text):
                notification_service.record_notification(db, user_id, "dept_head_digest", today)
    finally:
        db.close()


def _edu_department_payload(today: datetime.date) -> tuple[str, list[tuple[int, str]]]:
    # day_overview (внутри college_day_summary) сам исключает группы, для
    # которых сегодня не учебный день — см. пояснение выше.
    db = db_base.SessionLocal()
    try:
        summary = notification_service.college_day_summary(db, today)
        text = messages.edu_department_digest(summary, today)
        recipients = [
            (user.id, user.telegram_chat_id)
            for user in notification_service.edu_department_recipients(db)
            if not notification_service.was_notified(db, user.id, "edu_department_digest", today)
        ]
        return text, recipients
    finally:
        db.close()


async def send_edu_department_digest(bot: Bot, today: datetime.date | None = None) -> None:
    today = today or datetime.date.today()
    text, recipients = await asyncio.to_thread(_edu_department_payload, today)

    db = db_base.SessionLocal()
    try:
        for user_id, chat_id in recipients:
            if await _send(bot, chat_id, text):
                notification_service.record_notification(db, user_id, "edu_department_digest", today)
    finally:
        db.close()


def _leadership_payload(today: datetime.date) -> tuple[str, list[tuple[int, str]]]:
    db = db_base.SessionLocal()
    try:
        date_from = today - datetime.timedelta(days=6)
        digest = notification_service.leadership_weekly_digest(db, date_from, today)
        text = messages.leadership_digest(digest)
        recipients = [
            (user.id, user.telegram_chat_id)
            for user in notification_service.leadership_recipients(db)
            if not notification_service.was_notified(db, user.id, "leadership_digest", today)
        ]
        return text, recipients
    finally:
        db.close()


async def send_leadership_digest(bot: Bot, today: datetime.date | None = None) -> None:
    today = today or datetime.date.today()
    text, recipients = await asyncio.to_thread(_leadership_payload, today)

    db = db_base.SessionLocal()
    try:
        for user_id, chat_id in recipients:
            if await _send(bot, chat_id, text):
                notification_service.record_notification(db, user_id, "leadership_digest", today)
    finally:
        db.close()


def _cleanup(today: datetime.date) -> None:
    db = db_base.SessionLocal()
    try:
        counts = notification_service.cleanup_old_records(db, today)
        logger.info("Очистка старых записей: %s", counts)
    finally:
        db.close()


async def cleanup_old_records(bot: Bot | None = None, today: datetime.date | None = None) -> None:
    """Раньше не было ничего похожего (см. TODO.md 5) — старые прочитанные
    уведомления, записи notification_log и использованные/просроченные
    Telegram-токены копились бессрочно. `bot` не используется, но
    build_scheduler передаёт его во все задания одинаково."""
    today = today or datetime.date.today()
    await asyncio.to_thread(_cleanup, today)
