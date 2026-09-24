import datetime

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import RoleCode, StudyGroup, User
from app.models.people import CuratorAssignment

bearer_scheme = HTTPBearer(auto_error=False)

# С временным паролем (must_change_password=True) весь остальной API был
# доступен — проверка была только на фронтенде (см. TODO.md 2). Эти два
# пути остаются доступны, чтобы пользователь вообще мог узнать, кто он, и
# задать свой пароль.
_ALLOWED_WITH_PENDING_PASSWORD_CHANGE = {"/auth/me", "/auth/change-password"}


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужна авторизация")
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Токен недействителен")

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь не найден или заблокирован")
    # Токены, выпущенные до этого поля, не несут "tv" — считаем их версией 0,
    # совпадающей с начальным token_version у всех существующих пользователей
    # (см. миграцию f2a3b4c5d6e7), чтобы не разлогинить всех разом при деплое.
    if payload.get("tv", 0) != user.token_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия отозвана — войдите заново")
    if user.must_change_password and request.url.path not in _ALLOWED_WITH_PENDING_PASSWORD_CHANGE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Сначала задайте свой пароль")
    return user


def require_roles(*roles: RoleCode):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if RoleCode(user.role.code) not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
        return user

    return dependency


require_management = require_roles(RoleCode.DEPT_HEAD, RoleCode.EDU_DEPARTMENT, RoleCode.ADMIN, RoleCode.TUTOR)
# Справочники (коды отметок, календарь, сроки сдачи) — зона воспитательного
# отдела, а не зав. отделением (см. таблицу ролей в концепции).
require_reference_editor = require_roles(RoleCode.EDU_DEPARTMENT, RoleCode.ADMIN, RoleCode.TUTOR)
# Тьютор — второй полноценный администратор по всему колледжу (обновление
# 1.2), не отдельная урезанная роль: везде, где раньше был только admin,
# теперь и он. Имя оставлено как есть, чтобы не переименовывать во всех
# вызовах — по смыслу это "require_full_access".
require_admin = require_roles(RoleCode.ADMIN, RoleCode.TUTOR)


def scope_department_id(user: User, requested: int | None) -> int | None:
    """Зав. отделением всегда ограничен своим отделением, остальные — по
    запросу. Если у зав. отделением почему-то не задано отделение,
    возвращаем несуществующий id (а не None) — иначе фильтр по department_id
    просто не применяется и он видит весь колледж (см. TODO.md 1.4)."""
    if RoleCode(user.role.code) == RoleCode.DEPT_HEAD:
        if user.department_id is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "У вас не задано отделение — обратитесь к администратору"
            )
        return user.department_id
    return requested


def get_curator_group_ids(db: Session, user: User, on_date: datetime.date) -> list[int]:
    """Группы, которые ведёт пользователь (сам или как заместитель) на указанную дату."""
    assignments = (
        db.query(CuratorAssignment)
        .join(StudyGroup, StudyGroup.id == CuratorAssignment.study_group_id)
        # Архивная группа не должна оставаться в "Моих группах" куратора —
        # она снята с работы, отмечать в ней посещаемость больше не нужно
        # (см. TODO.md 3).
        .filter(CuratorAssignment.user_id == user.id, StudyGroup.is_active.is_(True))
        .all()
    )
    return [a.study_group_id for a in assignments if a.is_active_on(on_date)]


def assert_can_access_group(db: Session, user: User, study_group_id: int, on_date: datetime.date) -> None:
    role = RoleCode(user.role.code)
    if role in (RoleCode.DEPT_HEAD, RoleCode.EDU_DEPARTMENT, RoleCode.ADMIN, RoleCode.TUTOR):
        if role == RoleCode.DEPT_HEAD:
            group = db.get(StudyGroup, study_group_id)
            if group is None or group.department_id != user.department_id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Группа не относится к вашему отделению")
        return

    if study_group_id not in get_curator_group_ids(db, user, on_date):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Это не ваша группа")
