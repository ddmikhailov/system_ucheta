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
  - dept_head — только curator/deputy_curator своего отделения, и может
    назначать только роли curator/deputy_curator/dept_head (не может
    повысить кого-то до admin/tutor/edu_department или тронуть чужого
    dept_head/admin/tutor/edu_department, даже в своём отделении);
  - edu_department — не управляет учётками вообще (раньше могло сбросить
    пароль администратору — TODO.md 1.2).
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import RoleCode, Student, StudyGroup, User

ELEVATED_ROLES = {RoleCode.ADMIN.value, RoleCode.TUTOR.value}
DEPT_HEAD_MANAGEABLE_ROLES = {RoleCode.CURATOR.value, RoleCode.DEPUTY_CURATOR.value}
DEPT_HEAD_ASSIGNABLE_ROLES = {RoleCode.CURATOR.value, RoleCode.DEPUTY_CURATOR.value, RoleCode.DEPT_HEAD.value}
# Роли, которым обязательно нужно отделение, и роли, которым оно не нужно
# (см. TODO.md 1.4: без этого зав. отделением/куратор без отделения получает
# фактически доступ ко всему колледжу, т.к. фильтры по department_id=None
# просто не применяются).
DEPARTMENT_REQUIRED_ROLES = {RoleCode.DEPT_HEAD.value, RoleCode.CURATOR.value, RoleCode.DEPUTY_CURATOR.value}
DEPARTMENT_FORBIDDEN_ROLES = {RoleCode.ADMIN.value, RoleCode.TUTOR.value, RoleCode.EDU_DEPARTMENT.value}


def assert_can_manage_user(admin: User, target: User) -> None:
    if target.id == admin.id:
        return
    admin_role = RoleCode(admin.role.code)
    if admin_role == RoleCode.ADMIN:
        return
    if admin_role == RoleCode.TUTOR:
        if target.role.code in ELEVATED_ROLES:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Только администратор может управлять учётками администратора/тьютора"
            )
        return
    if admin_role == RoleCode.DEPT_HEAD:
        if admin.department_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "У вас не задано отделение — обратитесь к администратору")
        if target.department_id != admin.department_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Пользователь не относится к вашему отделению")
        if target.role.code not in DEPT_HEAD_MANAGEABLE_ROLES:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Зав. отделением может управлять только кураторами и заместителями"
            )
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для управления пользователями")


def assert_can_assign_role(admin: User, new_role_code: str) -> None:
    admin_role = RoleCode(admin.role.code)
    if admin_role == RoleCode.ADMIN:
        return
    if admin_role == RoleCode.DEPT_HEAD and new_role_code in DEPT_HEAD_ASSIGNABLE_ROLES:
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
    if RoleCode(user.role.code) == RoleCode.DEPT_HEAD and group.department_id != user.department_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Группа не относится к вашему отделению")


def assert_can_manage_student(db: Session, user: User, student: Student) -> None:
    if RoleCode(user.role.code) != RoleCode.DEPT_HEAD:
        return
    group = db.get(StudyGroup, student.study_group_id)
    if group is None or group.department_id != user.department_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Студент не из вашего отделения")
