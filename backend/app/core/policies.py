"""Правила «кто чем может управлять» — раньше были размазаны по admin.py
вперемешку с самими эндпоинтами (см. TODO.md 5). Логика не менялась при
переносе, только собрана в одно место, чтобы её было видно и проверять
целиком, а не по одной функции на файл роутера.

Права на управление учётками (пароль/логин/ФИО/архив/удаление) и на смену
ролей — см. TODO.md 1.2/1.3/1.5. Правило:
  - admin — управляет кем угодно, назначает любую роль;
  - tutor — как admin, но не может трогать учётки admin/tutor (иначе один
    тьютор мог бы захватить учётку другого тьютора или администратора) и
    не может менять роли вообще;
  - dept_head — как admin, но только в своём отделении: управляет любым пользователем своего
    отделения (кураторы, замы, соц. педагоги, психологи, тьюторы, воспитательный отдел, другие зав.
    отделением) и назначает любые роли с отделением; админов и ответственную по питанию (у них нет
    отделения) не трогает;
  - edu_department — в своём отделении только выдаёт временные пароли кураторам, замам, соц. педагогам
    и психологам (assert_can_manage_user); править, блокировать и удалять учётки не может
    (assert_can_edit_user).

Кто что видит (весь колледж, отделение или свои группы) — scope_of ниже; состав зон по ролям —
ROLE_SCOPES в core/roles.py.
"""
import datetime
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import false, true
from sqlalchemy.orm import Session

from app.core.roles import DEPARTMENT_LEADER_ROLES, ROLE_SCOPES, ScopeKind
from app.models import RoleCode, Student, StudyGroup, User
from app.services.access_service import led_group_ids

NO_DEPARTMENT_MESSAGE = "У вас не задано отделение — обратитесь к администратору"


@dataclass(frozen=True)
class Scope:
    """Зона видимости пользователя: весь колледж, одно отделение или группы, которые он ведёт.

    Раньше то же самое решали в каждом месте заново (свои кортежи ролей в deps, policies, сервисах
    задач, паспорта, питания), и правка прав расходилась: роль была «на весь колледж» в одних местах
    и «в отделении» в других. Теперь списки и проверки спрашивают зону, а не роль."""

    kind: ScopeKind
    department_id: int | None = None  # для DEPARTMENT; None — отделение не задано
    user_id: int | None = None  # для GROUPS

    @property
    def is_department(self) -> bool:
        return self.kind is ScopeKind.DEPARTMENT

    def within(self, department_id: int | None) -> bool:
        """Не выходит ли объект отделения department_id за пределы отделения пользователя. Для зон
        «колледж» и «группы» — да: кого вообще пускать к действию, решает ролевая зависимость эндпоинта."""
        if not self.is_department:
            return True
        return self.department_id is not None and department_id == self.department_id

    def in_department(self, department_id: int | None) -> bool:
        """Ограничен отделением, и объект — из этого отделения (руководитель отделения решает его запросы)."""
        return self.is_department and self.within(department_id)

    def department_or(self, requested: int | None) -> int | None:
        """Фильтр витрин и списков по отделению: ограниченным отделением — всегда своё (не задано —
        403, а не None: иначе фильтр не применился бы и открыл весь колледж), остальным — запрошенное."""
        if self.is_department:
            if self.department_id is None:
                raise HTTPException(status.HTTP_403_FORBIDDEN, NO_DEPARTMENT_MESSAGE)
            return self.department_id
        return requested

    def group_ids(self, db: Session, on_date: datetime.date) -> list[int]:
        return led_group_ids(db, self.user_id, on_date) if self.user_id is not None else []

    def group_filter(self, db: Session, on_date: datetime.date):
        """Условие на StudyGroup для запроса: какие группы в зоне."""
        if self.kind is ScopeKind.COLLEGE:
            return true()
        if self.is_department:
            return StudyGroup.department_id == self.department_id if self.department_id is not None else false()
        ids = self.group_ids(db, on_date)
        return StudyGroup.id.in_(ids) if ids else false()

    def require_group(self, db: Session, study_group_id: int, on_date: datetime.date) -> None:
        """403, если группа вне зоны (тексты ошибок — те, что показывает интерфейс)."""
        if self.kind is ScopeKind.COLLEGE:
            return
        if self.is_department:
            group = db.get(StudyGroup, study_group_id)
            if group is None or not self.within(group.department_id):
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Группа не относится к вашему отделению")
            return
        if study_group_id not in self.group_ids(db, on_date):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Это не ваша группа")


def scope_of(user: User, purpose: Literal["view", "edit"] = "view") -> Scope:
    """Зона пользователя для чтения (view) или для записи в журнал и планы группы (edit)."""
    view, edit = ROLE_SCOPES[RoleCode(user.role.code)]
    kind = view if purpose == "view" else edit
    if kind is ScopeKind.DEPARTMENT:
        return Scope(kind, department_id=user.department_id)
    if kind is ScopeKind.GROUPS:
        return Scope(kind, user_id=user.id)
    return Scope(kind)

ELEVATED_ROLES = {RoleCode.ADMIN.value, RoleCode.TUTOR.value}
# Кто может стереть студента/группу насовсем вместе с историей (зав. отделением — только в своём отделении,
# это проверяют assert_can_manage_group / assert_can_manage_student).
FORCE_DELETE_ROLES = ELEVATED_ROLES | {RoleCode.DEPT_HEAD.value}
# Кто может вести группу (быть назначен куратором/заместителем). Куратором человек
# становится назначением на группу, а не ролью: соц. педагог и психолог тоже ведут
# свои группы, оставаясь соц. педагогом/психологом.
CURATOR_CAPABLE_ROLES = {
    RoleCode.CURATOR.value, RoleCode.DEPUTY_CURATOR.value,
    RoleCode.SOCIAL_PEDAGOGUE.value, RoleCode.PSYCHOLOGIST.value,
}
# Зав. отделением, тьютор и воспитательный отдел (ограничены своим отделением) управляют кураторами,
# заместителями, соц. педагогами и психологами своего отделения.
DEPT_HEAD_MANAGEABLE_ROLES = {
    RoleCode.CURATOR.value, RoleCode.DEPUTY_CURATOR.value,
    RoleCode.SOCIAL_PEDAGOGUE.value, RoleCode.PSYCHOLOGIST.value,
}
DEPT_HEAD_ASSIGNABLE_ROLES = DEPT_HEAD_MANAGEABLE_ROLES | {
    RoleCode.DEPT_HEAD.value, RoleCode.TUTOR.value, RoleCode.EDU_DEPARTMENT.value,
}
TUTOR_ASSIGNABLE_ROLES = DEPT_HEAD_MANAGEABLE_ROLES
# Роли, которым обязательно нужно отделение, и роли, которым оно не нужно
# (см. TODO.md 1.4: без этого зав. отделением/куратор без отделения получает
# фактически доступ ко всему колледжу, т.к. фильтры по department_id=None
# просто не применяются).
DEPARTMENT_REQUIRED_ROLES = {
    RoleCode.DEPT_HEAD.value, RoleCode.TUTOR.value, RoleCode.EDU_DEPARTMENT.value,
    RoleCode.CURATOR.value, RoleCode.DEPUTY_CURATOR.value,
    RoleCode.SOCIAL_PEDAGOGUE.value, RoleCode.PSYCHOLOGIST.value,
}
DEPARTMENT_FORBIDDEN_ROLES = {RoleCode.ADMIN.value, RoleCode.MEAL_MANAGER.value}


def assert_can_manage_user(admin: User, target: User) -> None:
    if target.id == admin.id:
        return
    admin_role = RoleCode(admin.role.code)
    if admin_role == RoleCode.ADMIN:
        return
    scope = scope_of(admin)
    if scope.is_department:
        if scope.department_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, NO_DEPARTMENT_MESSAGE)
        if not scope.within(target.department_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Пользователь не относится к вашему отделению")
        if admin_role == RoleCode.DEPT_HEAD and target.role.code != RoleCode.ADMIN.value:
            # Как админ в своём отделении: любая роль, у которой есть отделение, включая воспитательный отдел.
            return
        if target.role.code not in DEPT_HEAD_MANAGEABLE_ROLES:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Можно управлять только кураторами, заместителями, соц. педагогами и психологами своего отделения"
            )
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для управления пользователями")


def assert_can_edit_user(admin: User, target: User) -> None:
    """Правка, блокировка и удаление учётной записи. То же, что assert_can_manage_user, но воспитательному отделу
    в своём отделении доступна только выдача временных паролей, а не управление учётками."""
    if target.id != admin.id and RoleCode(admin.role.code) == RoleCode.EDU_DEPARTMENT:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Воспитательный отдел может только выдавать временные пароли")
    assert_can_manage_user(admin, target)


def can_manage_user(admin: User, target: User) -> bool:
    """assert_can_manage_user без исключения — для расчёта получателей уведомлений."""
    try:
        assert_can_manage_user(admin, target)
    except HTTPException:
        return False
    return True


def assert_can_view_user(viewer: User, target: User) -> None:
    """Профиль пользователя (закрепления, дисциплина, журнал действий) — для чтения.
    Видят те же, кому виден список пользователей: администратор — всех, зав. отделением,
    тьютор и воспитательный отдел — людей своего отделения."""
    if target.id == viewer.id:
        return
    viewer_role = RoleCode(viewer.role.code)
    if viewer_role == RoleCode.ADMIN:
        return
    scope = scope_of(viewer)
    if scope.is_department:
        if scope.department_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, NO_DEPARTMENT_MESSAGE)
        if not scope.within(target.department_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Пользователь не относится к вашему отделению")
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для просмотра профиля")


def assert_can_review_attendance_change(user: User, group: StudyGroup) -> None:
    """Правку прошлого сданного дня куратором одобряет зав. отделением этой группы; тьютор —
    в своём отделении, администратор — в любом. Воспитательный отдел сам правит журнал, но
    чужие запросы не решает (так задумано: проверка — за руководителем отделения)."""
    role = RoleCode(user.role.code)
    if role == RoleCode.ADMIN:
        return
    if role in DEPARTMENT_LEADER_ROLES:
        if not scope_of(user).within(group.department_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Группа не относится к вашему отделению")
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Решать запросы на изменение посещаемости может зав. отделением")


def assert_can_review_student_deletion(user: User, group: StudyGroup) -> None:
    """Запрос куратора на полное удаление студента решает админ, а зав. отделением и тьютор — в своём отделении."""
    role = RoleCode(user.role.code)
    if role == RoleCode.ADMIN:
        return
    if role in DEPARTMENT_LEADER_ROLES:
        if not scope_of(user).within(group.department_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Студент не из вашего отделения")
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Решать запросы на удаление студентов может админ или зав. отделением")


URGENT_REPORT_READERS = (RoleCode.ADMIN, RoleCode.DEPT_HEAD, RoleCode.TUTOR, RoleCode.EDU_DEPARTMENT)


def assert_can_read_urgent_report(user: User, group: StudyGroup) -> None:
    """Срочное сообщение о студенте читают админ, зав. отделением, тьютор и воспитательный отдел — в своём отделении."""
    role = RoleCode(user.role.code)
    if role not in URGENT_REPORT_READERS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Срочные сообщения читает администрация отделения")
    if role != RoleCode.ADMIN and not scope_of(user).within(group.department_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Студент не из вашего отделения")


def assert_can_assign_role(admin: User, new_role_code: str) -> None:
    admin_role = RoleCode(admin.role.code)
    if admin_role == RoleCode.ADMIN:
        return
    if admin_role == RoleCode.DEPT_HEAD and new_role_code in DEPT_HEAD_ASSIGNABLE_ROLES:
        return
    if admin_role == RoleCode.TUTOR and new_role_code in TUTOR_ASSIGNABLE_ROLES:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для назначения этой роли")


def resolve_department_for_role(role_code: str, requested_department_id: int | None) -> int | None:
    """Отделение проставляется только там, где оно осмысленно (см. TODO.md
    1.3/1.4): у admin/tutor/edu_department его вообще не должно быть — форма
    создания пользователя раньше подставляла отделение всем без разбора."""
    if role_code in DEPARTMENT_FORBIDDEN_ROLES:
        return None
    if role_code in DEPARTMENT_REQUIRED_ROLES and requested_department_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Для этой роли нужно указать отделение")
    return requested_department_id


def assert_can_manage_group(user: User, group: StudyGroup) -> None:
    if not scope_of(user).within(group.department_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Группа не относится к вашему отделению")


def assert_can_manage_student(db: Session, user: User, student: Student) -> None:
    scope = scope_of(user)
    if not scope.is_department:
        return
    group = db.get(StudyGroup, student.study_group_id)
    if group is None or not scope.within(group.department_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Студент не из вашего отделения")
