"""Обратная связь из интерфейса: «Сообщить о проблеме» (уведомление администраторам в колокольчик) и ошибки
браузера (в журнал сервера и Sentry). Отдельный сервис не нужен: таблица уведомлений уже есть."""
import logging

from sqlalchemy.orm import Session

from app.core.observability import capture_client_error
from app.models import RoleCode, User
from app.schemas.support import ClientErrorRequest, ProblemReportRequest
from app.services.in_app_notification_service import notify

logger = logging.getLogger(__name__)

# Длина колонки in_app_notifications.message.
_MESSAGE_LIMIT = 500


def _shorten(value: str, limit: int) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def problem_message(user: User, payload: ProblemReportRequest) -> str:
    """Текст уведомления: кто, что написал и где. Текст человека режется первым, контекст — коротко."""
    context = " · ".join(
        part for part in (
            _shorten(payload.page, 80),
            f"версия {payload.version}" if payload.version else "",
            _shorten(payload.browser, 60),
            f"экран {payload.screen}" if payload.screen else "",
        ) if part
    )
    head = f"Сообщение о проблеме от {_shorten(user.full_name, 80)}: «"
    tail = f"»{f'. {context}' if context else ''}"
    return head + _shorten(payload.text, _MESSAGE_LIMIT - len(head) - len(tail)) + tail


def report_problem(db: Session, user: User, payload: ProblemReportRequest) -> int:
    """Уведомление каждому активному администратору; возвращает, скольким оно ушло."""
    admins = (
        db.query(User)
        .filter(User.role.has(code=RoleCode.ADMIN.value), User.is_active.is_(True))
        .all()
    )
    message = problem_message(user, payload)
    for admin in admins:
        notify(db, admin, "problem_report", message, entity_type="user", entity_id=str(user.id))
    # Текст человека в журнал сервера не пишем (там может быть ФИО студента), только сам факт.
    logger.info("Сообщение о проблеме: пользователь %s, страница %s, администраторов %s", user.id, payload.page, len(admins))
    return len(admins)


def report_client_error(user: User, payload: ClientErrorRequest) -> None:
    capture_client_error(
        payload.message,
        user_id=user.id,
        page=payload.page,
        version=payload.version,
        browser=payload.browser,
        screen=payload.screen,
        stack=payload.stack,
    )
