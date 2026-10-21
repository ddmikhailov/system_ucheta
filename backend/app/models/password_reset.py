import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base


class PasswordResetRequest(Base):
    """Запрос «Восстановить пароль» с экрана входа. Пока он открыт, получатели видят уведомление в
    колокольчике; выдача временного пароля любым из них закрывает запрос."""

    __tablename__ = "password_reset_requests"
    __table_args__ = (Index("ix_password_reset_requests_user_status", "user_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending | done
    requested_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
