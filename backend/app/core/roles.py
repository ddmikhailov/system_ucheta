"""Группы ролей и область видимости — единое место для api, сервисов и политик.

Раньше эти кортежи и проверки жили в app/api/deps.py, и сервисы (задачи, паспорт, импорт
досье) импортировали их из слоя API — обратная зависимость слоёв; в policies.py был ещё
один экземпляр того же кортежа.

Зеркало для интерфейса — frontend/src/constants/roles.ts: меняя состав групп, правьте оба."""
import enum

from app.models import RoleCode, User


class ScopeKind(str, enum.Enum):
    COLLEGE = "college"  # весь колледж
    DEPARTMENT = "department"  # своё отделение (не задано — не видно ничего)
    GROUPS = "groups"  # группы, которые человек ведёт сам или как заместитель


# Зона видимости каждой роли — единственное место, где она задаётся (policies.scope_of читает
# отсюда, группы ролей ниже выводятся отсюда же). Первое — чтение (журнал, витрины, досье, паспорт),
# второе — запись в журнал и планы группы.
#   - зав. отделением, тьютор и воспитательный отдел — своё отделение, тьютор — с полным доступом;
#   - соц. педагог и психолог читают досье, карточки и группы всего колледжа, а пишут только в
#     группах, которые ведут как кураторы; посещаемость и структуру не правят;
#   - ответственная по питанию к группам как к журналу доступа не имеет (вкладка «Питание» —
#     отдельно, MEAL_VIEW_ROLES).
ROLE_SCOPES: dict[RoleCode, tuple[ScopeKind, ScopeKind]] = {
    RoleCode.ADMIN: (ScopeKind.COLLEGE, ScopeKind.COLLEGE),
    RoleCode.SOCIAL_PEDAGOGUE: (ScopeKind.COLLEGE, ScopeKind.GROUPS),
    RoleCode.PSYCHOLOGIST: (ScopeKind.COLLEGE, ScopeKind.GROUPS),
    RoleCode.DEPT_HEAD: (ScopeKind.DEPARTMENT, ScopeKind.DEPARTMENT),
    RoleCode.TUTOR: (ScopeKind.DEPARTMENT, ScopeKind.DEPARTMENT),
    RoleCode.EDU_DEPARTMENT: (ScopeKind.DEPARTMENT, ScopeKind.DEPARTMENT),
    RoleCode.CURATOR: (ScopeKind.GROUPS, ScopeKind.GROUPS),
    RoleCode.DEPUTY_CURATOR: (ScopeKind.GROUPS, ScopeKind.GROUPS),
    RoleCode.MEAL_MANAGER: (ScopeKind.GROUPS, ScopeKind.GROUPS),
}

# Роли, ограниченные своим отделением.
DEPARTMENT_SCOPED_ROLES = tuple(r for r, (view, _) in ROLE_SCOPES.items() if view is ScopeKind.DEPARTMENT)

# Читают весь колледж, а пишут только в своих группах: соц. педагог и психолог.
DOSSIER_STAFF_ROLES = tuple(
    r for r, (view, edit) in ROLE_SCOPES.items() if view is ScopeKind.COLLEGE and edit is ScopeKind.GROUPS
)

# Кто видит группы, витрины и списки по всему колледжу, а не только свои группы.
COLLEGE_WIDE_ROLES = tuple(r for r, (view, _) in ROLE_SCOPES.items() if view is ScopeKind.COLLEGE)


# Руководители отделения: решают запросы своего отделения (правка сданного дня, полное удаление студента,
# проверка ответов на задачи «зав. отделением»). Воспитательный отдел видит то же отделение, но чужие запросы
# не решает — это полномочие, а не зона видимости, поэтому отдельный список.
DEPARTMENT_LEADER_ROLES = (RoleCode.DEPT_HEAD, RoleCode.TUTOR)


# Кто видит вкладку «Питание» (своды питающихся): администрация, воспитательный отдел, зав. отделением и тьютор
# (последние двое — только своё отделение, как в витринах посещаемости) и ответственная по питанию (весь колледж).
MEAL_VIEW_ROLES = (
    RoleCode.ADMIN, RoleCode.EDU_DEPARTMENT, RoleCode.DEPT_HEAD, RoleCode.TUTOR, RoleCode.MEAL_MANAGER,
)


def is_department_scoped(user: User) -> bool:
    return RoleCode(user.role.code) in DEPARTMENT_SCOPED_ROLES
