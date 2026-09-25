import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)

    # Отображаемое звание/должность — не роль с правами (те по-прежнему
    # определяются role_id), а просто подпись в интерфейсе. Пример из
    # обновления 1.1: сотрудник с правами зав. отделением, но должность
    # по штату — «Советник директора по воспитанию». Пусто — показываем
    # стандартное название роли.
    display_title: Mapped[str | None] = mapped_column(String(128), nullable=True)

    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    telegram_linked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    # Администратор/зав. отделением выдал временный пароль — при следующем
    # входе пользователь обязан задать свой собственный (см. концепцию
    # обновления 1.1: отказ от одноразовых пригласительных ссылок).
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Увеличивается при сбросе/смене пароля, смене роли и архивации — уже
    # выданные JWT со старым значением в claim "tv" перестают приниматься
    # немедленно, а не только через 12 часов по истечении срока (см.
    # TODO.md 2: раньше отозвать выданный токен было нечем).
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # "Руководство" из раздела про бота — не отдельная роль с правами доступа,
    # а просто список получателей пятничного дайджеста (см. концепцию).
    receives_leadership_digest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    role: Mapped["Role"] = relationship(back_populates="users")
    department: Mapped["Department"] = relationship()
    curator_assignments: Mapped[list["CuratorAssignment"]] = relationship(back_populates="user")

    @property
    def is_locked(self) -> bool:
        return self.locked_until is not None and self.locked_until > utcnow()
