import { PLATFORM_NAME } from "../constants/brand";

// Заголовок страницы: невидимый h1 для экранного диктора и название вкладки браузера.
const PAGE_TITLES: [string, string][] = [
  ["/my-day", "Мой день"],
  ["/cabinet", "Мои группы"],
  ["/my-tasks", "Мои задачи"],
  ["/tasks/assignment", "Задача"],
  ["/tasks", "Задачи"],
  ["/dashboards", "Витрины"],
  ["/admin/users/", "Профиль пользователя"],
  ["/admin", "Администрирование"],
  ["/students/", "Карточка студента"],
  ["/students", "Студенты"],
  ["/passport", "Социальный паспорт"],
  ["/individual-work", "Индивидуальная работа"],
  ["/plan", "План воспитательной работы"],
  ["/report", "Отчёт куратора"],
];

export function pageTitle(pathname: string): string {
  return PAGE_TITLES.find(([prefix]) => pathname === prefix || pathname.startsWith(prefix.endsWith("/") ? prefix : `${prefix}/`))?.[1] ?? PLATFORM_NAME;
}
