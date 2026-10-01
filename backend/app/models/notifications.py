import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base


class InAppNotification(Base):
    """Уведомления внутри платформы — колокольчик в шапке (обновление 1.1).

    Единственный канал уведомлений: события вроде «куратор отредактировал
    день задним числом» зав. отделением видит в колокольчике.
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
