// Единый источник правды по ролям в интерфейсе. Раньше литералы вроде
// `user.role === "dept_head" || user.role === "tutor"` и списки ролей повторялись
// в десятке файлов и расходились при каждом изменении прав.
// Зеркало на бэкенде — backend/app/core/roles.py и app/core/policies.py: меняя состав групп,
// правьте оба места.

export const ROLE = {
  CURATOR: "curator",
  DEPUTY_CURATOR: "deputy_curator",
  DEPT_HEAD: "dept_head",
  EDU_DEPARTMENT: "edu_department",
  ADMIN: "admin",
  TUTOR: "tutor",
  SOCIAL_PEDAGOGUE: "social_pedagogue",
  PSYCHOLOGIST: "psychologist",
} as const;

export type RoleCode = (typeof ROLE)[keyof typeof ROLE];

export const ROLE_LABELS: Record<RoleCode, string> = {
  curator: "Куратор",
  deputy_curator: "Заместитель куратора",
  dept_head: "Зав. отделением",
  edu_department: "Воспитательный отдел",
  admin: "Администратор",
  tutor: "Тьютор",
  social_pedagogue: "Социальный педагог",
  psychologist: "Педагог-психолог",
};

type Roles = readonly string[];

/** Куратор и заместитель куратора. */
export const TEACHER_ROLES: Roles = [ROLE.CURATOR, ROLE.DEPUTY_CURATOR];

/** Соц. педагог и психолог: все группы и досье всех студентов колледжа, только просмотр
 * посещаемости, без админки (backend: DOSSIER_STAFF_ROLES). */
export const DOSSIER_STAFF_ROLES: Roles = [ROLE.SOCIAL_PEDAGOGUE, ROLE.PSYCHOLOGIST];

/** Роли, ограниченные своим отделением (backend: DEPARTMENT_SCOPED_ROLES). */
export const DEPARTMENT_SCOPED_ROLES: Roles = [ROLE.DEPT_HEAD, ROLE.TUTOR];

/** Роли с доступом к админке и витринам управленца. */
export const MANAGEMENT_ROLES: Roles = [ROLE.DEPT_HEAD, ROLE.EDU_DEPARTMENT, ROLE.ADMIN, ROLE.TUTOR];

/** Кто видит витрины, поиск студентов и соц. паспорт всех групп. */
export const VIEWER_ROLES: Roles = [...MANAGEMENT_ROLES, ...DOSSIER_STAFF_ROLES];

/** Кто ставит и проверяет задачи (backend: TASK_MANAGER_ROLES). */
export const TASK_MANAGER_ROLES: Roles = [ROLE.ADMIN, ROLE.EDU_DEPARTMENT, ROLE.TUTOR, ROLE.DEPT_HEAD];

/** Кого можно назначать куратором/заместителем группы (backend: CURATOR_CAPABLE_ROLES). */
export const CURATOR_CAPABLE_ROLES: Roles = [...TEACHER_ROLES, ...DOSSIER_STAFF_ROLES];

/** Кто правит структуру (группы, студенты, пользователи): админ — по колледжу, остальные — в своём отделении. */
export const STRUCTURE_EDITOR_ROLES: Roles = [ROLE.ADMIN, ROLE.TUTOR, ROLE.DEPT_HEAD];

/** Кто правит общий календарь и коды отметок. */
export const REFERENCE_EDITOR_ROLES: Roles = [ROLE.ADMIN, ROLE.EDU_DEPARTMENT];

/** Кто видит все отделения колледжа (фильтр по отделению в витринах и паспорте). */
export const COLLEGE_WIDE_ROLES: Roles = [ROLE.ADMIN, ROLE.EDU_DEPARTMENT, ...DOSSIER_STAFF_ROLES];

/** Кто видит журнал просмотров досье (по студентам своей области доступа). */
export const DOSSIER_AUDIT_ROLES: Roles = [ROLE.ADMIN, ROLE.TUTOR];

/** Роли, которым отделение обязательно (backend: DEPARTMENT_REQUIRED_ROLES). */
export const DEPARTMENT_REQUIRED_ROLES: Roles = [
  ROLE.DEPT_HEAD, ROLE.TUTOR, ROLE.CURATOR, ROLE.DEPUTY_CURATOR, ROLE.SOCIAL_PEDAGOGUE, ROLE.PSYCHOLOGIST,
];

/** Какие роли может назначать пользователь с ролью `myRole` (backend: assert_can_assign_role). */
export function assignableRoles(myRole: string | undefined): RoleCode[] {
  if (myRole === ROLE.ADMIN) return Object.values(ROLE);
  if (myRole === ROLE.DEPT_HEAD) return [...TEACHER_ROLES, ...DOSSIER_STAFF_ROLES, ROLE.DEPT_HEAD] as RoleCode[];
  if (myRole === ROLE.TUTOR) return [...TEACHER_ROLES, ...DOSSIER_STAFF_ROLES] as RoleCode[];
  return [];
}

/** Роль входит в группу ролей; `undefined` (не вошёл) — не входит. */
export function inRoles(role: string | undefined | null, group: Roles): boolean {
  return role != null && group.includes(role);
}

interface WithRole {
  role: string;
  groups?: unknown[];
}

/** Ведёт ли пользователь группы: куратор/заместитель по роли либо любой, кому назначена группа
 * (соц. педагог/психолог тоже могут вести свои группы). */
export function leadsGroups(user: WithRole | null | undefined): boolean {
  return !!user && (inRoles(user.role, TEACHER_ROLES) || (user.groups?.length ?? 0) > 0);
}
