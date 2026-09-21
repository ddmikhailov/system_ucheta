import datetime


def utcnow() -> datetime.datetime:
    """Наивный UTC-datetime — так же, как раньше давал datetime.utcnow(),
    но без предупреждения об устаревании в новых версиях Python. Колонки в
    БД — обычный DATETIME без таймзоны, поэтому tzinfo сознательно убран."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
