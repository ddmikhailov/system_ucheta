"""Мониторинг ошибок (см. TODO.md 5) — вынесено в отдельную функцию, чтобы
её можно было вызвать (и протестировать) без побочных эффектов импорта
app.main целиком."""
from app.core.config import Settings


def init_sentry(settings: Settings) -> bool:
    """Без DSN — no-op (возвращает False): раньше единственным способом
    узнать о 500-й ошибке было зайти в логи контейнера руками, теперь
    достаточно задать SENTRY_DSN одной переменной окружения."""
    if not settings.sentry_dsn:
        return False

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        environment=settings.environment,
        traces_sample_rate=0.1,
    )
    return True
