import datetime

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.roles import DEPARTMENT_SCOPED_ROLES, DOSSIER_STAFF_ROLES, is_department_scoped
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import RoleCode, StudyGroup, User
from app.services.access_service import get_curator_group_ids

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
# Справочники общие на весь колледж — тьютор (он ограничен своим отделением) их не правит.
require_reference_editor = require_roles(RoleCode.EDU_DEPARTMENT, RoleCode.ADMIN)
# Тьютор — второй полноценный администратор по всему колледжу (обновление
# 1.2), не отдельная урезанная роль: везде, где раньше был только admin,
# теперь и он. Название отражает это явно (было require_admin — вводило в
# заблуждение, будто пускает только администратора, см. TODO.md 5).
require_full_access = require_roles(RoleCode.ADMIN)
# Создавать группы/студентов/пользователей: администратор по колледжу, зав. отделением и тьютор — в своём отделении.
require_dept_editor = require_roles(RoleCode.ADMIN, RoleCode.TUTOR, RoleCode.DEPT_HEAD)
# Исключения календаря для конкретной группы: воспитательный отдел и администратор — для любой,
# зав. отделением и тьютор — для групп своего отделения (проверка группы — в эндпоинте).
require_group_calendar_editor = require_roles(
    RoleCode.EDU_DEPARTMENT, RoleCode.ADMIN, RoleCode.TUTOR, RoleCode.DEPT_HEAD
)

# Правка/удаление групп и студентов — админ/тьютор по колледжу и зав.
# отделением в своём отделении. Воспитательный отдел структуру не правит
# (в интерфейсе у него эти вкладки только для чтения), раньше бэкенд
# пускал его через require_management.
require_structure_editor = require_roles(RoleCode.ADMIN, RoleCode.TUTOR, RoleCode.DEPT_HEAD)

# Просмотр групп, витрин и списка групп: управленческие роли + соц. педагог и
# психолог (по всему колледжу, только чтение). Всё, что меняет данные, остаётся
# за require_management / require_structure_editor.
require_viewer = require_roles(
    RoleCode.DEPT_HEAD, RoleCode.EDU_DEPARTMENT, RoleCode.ADMIN, RoleCode.TUTOR, *DOSSIER_STAFF_ROLES
)


def scope_department_id(user: User, requested: int | None) -> int | None:
    """Зав. отделением всегда ограничен своим отделением, остальные — по
    запросу. Если у зав. отделением почему-то не задано отделение,
    возвращаем несуществующий id (а не None) — иначе фильтр по department_id
    просто не применяется и он видит весь колледж (см. TODO.md 1.4)."""
    if is_department_scoped(user):
        if user.department_id is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "У вас не задано отделение — обратитесь к администратору"
            )
        return user.department_id
    return requested


MAX_DATE_RANGE_DAYS = 366 * 2


def validate_date_range(
    date_from: datetime.date, date_to: datetime.date, max_days: int = MAX_DATE_RANGE_DAYS
) -> None:
    """Витрины/экспорт принимали любой диапазон дат без ограничения — запрос
    за 100 лет клал бы сервер (см. TODO.md 5). 2 года с запасом покрывает
    любой практический сценарий (учебный год + межгодовое сравнение)."""
    if date_from > date_to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_from не может быть позже date_to")
    if (date_to - date_from).days > max_days:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Диапазон дат не может превышать {max_days} дней")


def assert_can_view_group(db: Session, user: User, study_group_id: int, on_date: datetime.date) -> None:
    """Только чтение: как assert_can_access_group, но соц. педагог и психолог
    видят любую группу колледжа."""
    if RoleCode(user.role.code) in DOSSIER_STAFF_ROLES:
        return
    assert_can_access_group(db, user, study_group_id, on_date)


def assert_can_access_group(db: Session, user: User, study_group_id: int, on_date: datetime.date) -> None:
    role = RoleCode(user.role.code)
    if role in (RoleCode.DEPT_HEAD, RoleCode.EDU_DEPARTMENT, RoleCode.ADMIN, RoleCode.TUTOR):
        if role in DEPARTMENT_SCOPED_ROLES:
            group = db.get(StudyGroup, study_group_id)
            if group is None or user.department_id is None or group.department_id != user.department_id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Группа не относится к вашему отделению")
        return

    if study_group_id not in get_curator_group_ids(db, user, on_date):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Это не ваша группа")
