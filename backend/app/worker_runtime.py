"""Общая логика запуска бота и планировщика — используется и точечными
процессами (bot/main.py, scheduler/main.py) для раздельного разворачивания,
и встроенным режимом (app.main, через lifespan) для единого приложения,
который включён по умолчанию (см. EMBED_WORKERS в конфиге). Раздельный
режим существует на случай, если проект вырастет настолько, что рассылки
пора выносить на отдельный ресурс — держать его в одном месте, а не
дублировать в двух рантаймах.
"""
import logging

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from bot.handlers import router as bot_router
from scheduler import jobs

logger = logging.getLogger(__name__)


def _parse_hh_mm(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(bot_router)
    return dispatcher


async def run_bot_polling(bot: Bot) -> None:
    dispatcher = build_dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)
    await dispatcher.start_polling(bot)


def build_scheduler(bot: Bot) -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone=settings.notification_timezone)

    first_hour, first_minute = _parse_hh_mm(settings.reminder_first_time)
    second_hour, second_minute = _parse_hh_mm(settings.reminder_second_time)
    dept_hour, dept_minute = _parse_hh_mm(settings.dept_head_digest_time)
    edu_hour, edu_minute = _parse_hh_mm(settings.edu_department_digest_time)
    lead_hour, lead_minute = _parse_hh_mm(settings.leadership_digest_time)

    scheduler.add_job(
        jobs.send_first_reminder, CronTrigger(hour=first_hour, minute=first_minute), args=[bot],
        id="reminder_1", misfire_grace_time=3600,
    )
    scheduler.add_job(
        jobs.send_second_reminder, CronTrigger(hour=second_hour, minute=second_minute), args=[bot],
        id="reminder_2", misfire_grace_time=3600,
    )
    scheduler.add_job(
        jobs.send_dept_head_digest, CronTrigger(hour=dept_hour, minute=dept_minute), args=[bot],
        id="dept_head_digest", misfire_grace_time=3600,
    )
    scheduler.add_job(
        jobs.send_edu_department_digest, CronTrigger(hour=edu_hour, minute=edu_minute), args=[bot],
        id="edu_department_digest", misfire_grace_time=3600,
    )
    scheduler.add_job(
        jobs.send_leadership_digest,
        CronTrigger(day_of_week="fri", hour=lead_hour, minute=lead_minute),
        args=[bot], id="leadership_digest", misfire_grace_time=3600,
    )
    return scheduler
