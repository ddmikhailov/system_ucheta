// Выключаемые модули платформы (релиз 3.5.0). Набор включённых приходит с сервера в /auth/me (`modules`),
// задаёт его переменная ENABLED_MODULES. Зеркало бэкенда — backend/app/core/modules.py: меняя список,
// правьте оба места (сверяет tests/test_frontend_roles_contract.py).

export const MODULE = {
  ATTENDANCE: "attendance",
  TASKS: "tasks",
  MY_ID: "my_id",
  MEALS: "meals",
  DOSSIER: "dossier",
  PASSPORT: "passport",
  INDIVIDUAL_WORK: "individual_work",
  PLAN: "plan",
  MEETINGS: "meetings",
  REPORTS: "reports",
} as const;

export type ModuleName = (typeof MODULE)[keyof typeof MODULE];

/** Релизный набор: что включено, пока ENABLED_MODULES не задана (backend: RELEASE_MODULES). */
export const RELEASE_MODULES: readonly ModuleName[] = [
  MODULE.ATTENDANCE,
  MODULE.TASKS,
  MODULE.MY_ID,
  MODULE.MEALS,
  MODULE.DOSSIER,
  MODULE.INDIVIDUAL_WORK,
];
