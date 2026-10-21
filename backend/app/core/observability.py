"""Мониторинг ошибок (Sentry или совместимый с ним GlitchTip) — вынесено в отдельную функцию, чтобы
её можно было вызвать (и протестировать) без побочных эффектов импорта app.main целиком.

Персональные данные наружу не уходят (152-ФЗ): ни тела запросов, ни cookie и заголовки, ни строка запроса,
ни локальные переменные в стеке, ни параметры SQL-запросов. Остаётся то, что нужно для разбора ошибки:
метод и путь, тип исключения, стек по строкам кода, номер пользователя."""
import logging
import re

from app.core.config import Settings

logger = logging.getLogger(__name__)

# SQLAlchemy дописывает значения параметров к тексту ошибки («[parameters: ('Иванов', ...)]»; движок создаётся
# с hide_parameters=True, это вторая линия), а MySQL повторяет значение в «Duplicate entry '...' for key».
_SQL_PARAMETERS = re.compile(r"\[parameters: .*?(?=\n\(Background|\Z)", re.S)
_DUPLICATE_ENTRY = re.compile(r"Duplicate entry '.*?' for key", re.S)


def scrub_event(event: dict, hint: dict | None = None) -> dict:
    """before_send: вычищает из события всё, что может содержать ФИО и другие ПДн."""
    request = event.get("request")
    if isinstance(request, dict):
        event["request"] = {key: request[key] for key in ("method", "url") if key in request}
    user = event.get("user")
    if isinstance(user, dict):
        event["user"] = {"id": user["id"]} if "id" in user else {}
    breadcrumbs = event.get("breadcrumbs")
    crumbs = breadcrumbs.get("values", []) if isinstance(breadcrumbs, dict) else breadcrumbs or []
    for crumb in crumbs:
        if isinstance(crumb, dict):
            crumb.pop("data", None)
    for exception in (event.get("exception") or {}).get("values", []):
        if isinstance(exception.get("value"), str):
            value = _SQL_PARAMETERS.sub("[parameters: скрыты]", exception["value"])
            exception["value"] = _DUPLICATE_ENTRY.sub("Duplicate entry '…' for key", value)
        for frame in (exception.get("stacktrace") or {}).get("frames", []):
            frame.pop("vars", None)
    return event


def init_sentry(settings: Settings, release: str | None = None) -> bool:
    """Без DSN — no-op (возвращает False): раньше единственным способом
    узнать о 500-й ошибке было зайти в логи сервера руками, теперь
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
        release=release,
        traces_sample_rate=0.1,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        before_send=scrub_event,
    )
    return True


def capture_client_error(
    message: str, *, user_id: int, page: str, version: str, browser: str, screen: str, stack: str,
) -> None:
    """Ошибка JavaScript из браузера: в журнал сервера всегда, в Sentry — если он подключён. Без этого об
    ошибках интерфейса (белый экран, кнопка не нажимается) узнавали только со слов кураторов."""
    logger.warning("Ошибка в интерфейсе: %s | страница %s | версия %s | %s | пользователь %s", message, page, version, browser, user_id)
    import sentry_sdk

    if not sentry_sdk.is_initialized():
        return
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("source", "frontend")
        scope.set_tag("page", page[:200])
        scope.set_tag("frontend_version", version)
        scope.set_user({"id": user_id})
        scope.set_context("browser_report", {"browser": browser, "screen": screen, "stack": stack})
        sentry_sdk.capture_message(f"Ошибка в интерфейсе: {message}", level="error")
