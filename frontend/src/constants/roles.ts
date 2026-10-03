// Раньше был продублирован дословно в App.tsx, Layout.tsx и
// NotificationBell.tsx (см. TODO.md 5) — роли, которые видят
// админку/витрины, а не только личный кабинет куратора.
export const MANAGEMENT_ROLES = ["dept_head", "edu_department", "admin", "tutor"];

// Соц. педагог и психолог: все группы и досье всех студентов колледжа, только
// просмотр посещаемости, без админки (зеркалит DOSSIER_STAFF_ROLES на бэкенде).
export const DOSSIER_STAFF_ROLES = ["social_pedagogue", "psychologist"];

// Кого можно назначать куратором/заместителем группы (зеркалит CURATOR_CAPABLE_ROLES).
export const CURATOR_CAPABLE_ROLES = ["curator", "deputy_curator", ...DOSSIER_STAFF_ROLES];

// Кто ставит и проверяет задачи (зеркалит TASK_MANAGER_ROLES на бэкенде).
export const TASK_MANAGER_ROLES = ["admin", "edu_department", "tutor", "dept_head"];

// Кто видит витрины и поиск студентов.
export const VIEWER_ROLES = [...MANAGEMENT_ROLES, ...DOSSIER_STAFF_ROLES];
