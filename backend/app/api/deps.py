import datetime

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import RoleCode, StudyGroup, User
from app.models.people import CuratorAssignment

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
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
    return user


def require_roles(*roles: RoleCode):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if RoleCode(user.role.code) not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
        return user

    return dependency


require_management = require_roles(RoleCode.DEPT_HEAD, RoleCode.EDU_DEPARTMENT, RoleCode.ADMIN)
# Справочники (коды отметок, календарь, сроки сдачи) — зона воспитательного
# отдела, а не зав. отделением (см. таблицу ролей в концепции).
require_reference_editor = require_roles(RoleCode.EDU_DEPARTMENT, RoleCode.ADMIN)
require_admin = require_roles(RoleCode.ADMIN)


def get_curator_group_ids(db: Session, user: User, on_date: datetime.date) -> list[int]:
    """Группы, которые ведёт пользователь (сам или как заместитель) на указанную дату."""
    assignments = (
        db.query(CuratorAssignment)
        .filter(CuratorAssignment.user_id == user.id)
        .all()
    )
    return [a.study_group_id for a in assignments if a.is_active_on(on_date)]


def assert_can_access_group(db: Session, user: User, study_group_id: int, on_date: datetime.date) -> None:
    role = RoleCode(user.role.code)
    if role in (RoleCode.DEPT_HEAD, RoleCode.EDU_DEPARTMENT, RoleCode.ADMIN):
        if role == RoleCode.DEPT_HEAD:
            group = db.get(StudyGroup, study_group_id)
            if group is None or group.department_id != user.department_id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Группа не относится к вашему отделению")
        return

    if study_group_id not in get_curator_group_ids(db, user, on_date):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Это не ваша группа")
