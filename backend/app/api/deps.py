import datetime

import jwt
from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, joinedload

from app.core.policies import scope_of
from app.core.roles import DOSSIER_STAFF_ROLES, MEAL_VIEW_ROLES
from app.core.config import get_settings
from app.core.modules import module_enabled
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import RoleCode, User

bearer_scheme = HTTPBearer(auto_error=False)

# С временным паролем (must_change_password=True) весь остальной API был
# доступен — проверка была только на фронтенде (см. TODO.md 2). Эти два
# пути остаются доступны, чтобы пользователь вообще мог узнать, кто он, и
# задать свой пароль.
_ALLOWED_WITH_PENDING_PASSWORD_CHANGE = {"/auth/me", "/auth/change-password", "/auth/logout", "/auth/logout-all"}

# Защита от CSRF для входа по cookie: браузер подставляет cookie в любой запрос к
# нашему домену, в том числе с чужой страницы. Чужая страница не может добавить
# нестандартный заголовок без CORS-preflight (а он отклоняется), поэтому для
# изменяющих запросов с cookie требуем этот заголовок; SameSite=Strict — вторая линия.
CSRF_HEADER = "x-requested-with"
CSRF_HEADER_VALUE = "kait20"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def extract_token(
    request: Request, credentials: HTTPAuthorizationCredentials | None, session_cookie: str | None
) -> str | None:
    """Токен из Authorization: Bearer (скрипты, тесты) либо из cookie сессии (браузер)."""
    if credentials is not None:
        return credentials.credentials
    if session_cookie:
        if request.method not in _SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_HEADER_VALUE:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Запрос отклонён: нет заголовка защиты от CSRF")
        return session_cookie
    return None


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session_cookie: str | None = Cookie(default=None, alias=get_settings().session_cookie_name),
    db: Session = Depends(get_db),
) -> User:
    token = extract_token(request, credentials, session_cookie)
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужна авторизация")
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Токен недействителен")

    # Роль нужна почти каждому эндпоинту — грузим вместе с пользователем, а не вторым запросом.
    user = db.get(User, int(payload["sub"]), options=[joinedload(User.role)])
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


def require_module(name: str):
    """Зависимость для отдельных эндпоинтов внутри «всегда включённого» роутера: модуль выключен — 404, как будто
    такого адреса нет (целые роутеры выключенных модулей просто не подключаются, см. main.MODULE_ROUTERS)."""
    def dependency() -> None:
        if not module_enabled(name):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Раздел отключён")

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
require_meal_viewer = require_roles(*MEAL_VIEW_ROLES)
require_viewer = require_roles(
    RoleCode.DEPT_HEAD, RoleCode.EDU_DEPARTMENT, RoleCode.ADMIN, RoleCode.TUTOR, *DOSSIER_STAFF_ROLES
)


def scope_department_id(user: User, requested: int | None) -> int | None:
    """Фильтр по отделению для витрин и списков — см. policies.Scope.department_or."""
    return scope_of(user).department_or(requested)


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
    """Только чтение группы (журнал, планы, отчёты): зона «view» — соц. педагог и психолог видят
    любую группу колледжа."""
    scope_of(user, "view").require_group(db, study_group_id, on_date)


def assert_can_access_group(db: Session, user: User, study_group_id: int, on_date: datetime.date) -> None:
    """Запись в журнал и планы группы: зона «edit» — соц. педагог и психолог только в своих группах."""
    scope_of(user, "edit").require_group(db, study_group_id, on_date)
