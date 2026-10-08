"""Группы ролей и область видимости — единое место для api, сервисов и политик.

Раньше эти кортежи и проверки жили в app/api/deps.py, и сервисы (задачи, паспорт, импорт
досье) импортировали их из слоя API — обратная зависимость слоёв; в policies.py был ещё
один экземпляр того же кортежа.

Зеркало для интерфейса — frontend/src/constants/roles.ts: меняя состав групп, правьте оба."""
from app.models import RoleCode, User

# Роли, ограниченные своим отделением: зав. отделением и тьютор. Тьютор — полный доступ,
# но только к своему отделению (группы, студенты, досье, кураторы).
DEPARTMENT_SCOPED_ROLES = (RoleCode.DEPT_HEAD, RoleCode.TUTOR)

# Соц. педагог и психолог: досье и карточка любого студента колледжа, просмотр всех групп,
# но не посещаемость/структура (запись посещаемости — только в группах, которые они ведут
# как кураторы).
DOSSIER_STAFF_ROLES = (RoleCode.SOCIAL_PEDAGOGUE, RoleCode.PSYCHOLOGIST)

# Кто видит группы, витрины и списки по всему колледжу, а не только свои группы.
COLLEGE_WIDE_ROLES = (RoleCode.ADMIN, RoleCode.EDU_DEPARTMENT, *DOSSIER_STAFF_ROLES)


# Кто видит вкладку «Питание» (своды питающихся): администрация, воспитательный отдел, зав. отделением и тьютор
# (последние двое — только своё отделение, как в витринах посещаемости) и ответственная по питанию (весь колледж).
MEAL_VIEW_ROLES = (
    RoleCode.ADMIN, RoleCode.EDU_DEPARTMENT, RoleCode.DEPT_HEAD, RoleCode.TUTOR, RoleCode.MEAL_MANAGER,
)


def is_department_scoped(user: User) -> bool:
    return RoleCode(user.role.code) in DEPARTMENT_SCOPED_ROLES
