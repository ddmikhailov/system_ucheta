import datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def utcnow() -> datetime.datetime:
    """Наивный UTC-datetime — так же, как раньше давал datetime.utcnow(),
    но без предупреждения об устаревании в новых версиях Python. Колонки в
    БД — обычный DATETIME без таймзоны, поэтому tzinfo сознательно убран."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def today_local() -> datetime.date:
    """«Сегодня» с точки зрения пользователей колледжа (`NOTIFICATION_TIMEZONE`,
    по умолчанию Europe/Moscow), а не сервера. Сервер обычно работает в UTC —
    без этого с ~21:00 до 23:59 UTC (то есть уже "завтра" в Москве) проверки
    вроде "нельзя редактировать будущую дату" или расчёт дня календаря на
    несколько часов расходились с тем, что видит куратор на экране (см.
    TODO.md 3)."""
    settings = get_settings()
    return datetime.datetime.now(ZoneInfo(settings.notification_timezone)).date()
