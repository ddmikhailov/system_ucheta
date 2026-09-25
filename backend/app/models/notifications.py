import datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base


class TelegramLinkToken(Base):
    """Одноразовая ссылка t.me/бот?start=<token> для подключения Telegram.

    Куратор сам решает, подключать ли Telegram (см. концепцию) — токен
    создаётся только по явному действию уже авторизованного пользователя
    в личном кабинете, а не администратором.
    """

    __tablename__ = "telegram_link_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user: Mapped["User"] = relationship()

    @property
    def is_usable(self) -> bool:
        return self.used_at is None and self.expires_at > utcnow()


class InAppNotification(Base):
    """Уведомления внутри платформы — колокольчик в шапке (обновление 1.1).

    Пока это единственный канал: Telegram скрыт из интерфейса, значит
    события вроде «куратор отредактировал день задним числом» должны быть
    видны где-то ещё, иначе зав. отделением о них просто не узнает.
    """

    __tablename__ = "in_app_notifications"
    __table_args__ = (Index("ix_in_app_notifications_user_read", "user_id", "read_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    read_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship()


class NotificationLog(Base):
    """Кому и когда что отправлено — планировщик сверяется с этим перед
    отправкой, чтобы перезапуск не задвоил напоминание и не нарушил лимит
    «не больше двух напоминаний в день одному человеку»."""

    __tablename__ = "notification_log"
    __table_args__ = (UniqueConstraint("user_id", "kind", "date", name="uq_notification_once"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    sent_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user: Mapped["User"] = relationship()
