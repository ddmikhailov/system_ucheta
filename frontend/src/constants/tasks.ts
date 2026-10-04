export const TASK_STATUS_LABELS: Record<string, string> = {
  new: "Не начато",
  in_progress: "В работе",
  submitted: "На проверке",
  returned: "Возвращено",
  accepted: "Принято",
};

export const HISTORY_LABELS: Record<string, string> = {
  submitted: "Отправлено на проверку",
  accepted: "Принято",
  returned: "Возвращено на доработку",
  auto_accepted: "Принято автоматически (проверка не требуется)",
};

export const COLLECT_MODE_LABELS: Record<string, string> = {
  group: "Ответ по группе",
  student: "По каждому студенту",
  selected: "По выбранным студентам",
};

export const REVIEWER_LABELS: Record<string, string> = {
  dept_head: "Зав. отделением группы",
  edu_department: "Воспитательный отдел",
  two_step: "Две ступени: зав. отделением → воспитательный отдел",
  author: "Автор задачи",
  none: "Без проверки",
};

export const FIELD_TYPE_LABELS: Record<string, string> = {
  text: "Текст",
  number: "Число",
  date: "Дата",
  bool: "Да / нет",
  select: "Выбор из списка",
  multiselect: "Множественный выбор",
  link: "Ссылка",
};

// Повторный запуск задач по шаблону.
export const REPEAT_LABELS: Record<string, string> = {
  "": "Не повторять",
  monthly: "Каждый месяц",
  semester: "Каждый семестр (сентябрь и февраль)",
};

export function scheduleText(t: { repeat: string; repeat_day: number; due_offset_days: number }): string {
  if (t.repeat === "monthly") return `Каждый месяц, ${t.repeat_day}-го числа; срок — через ${t.due_offset_days} дн.`;
  if (t.repeat === "semester") return `Каждый семестр (сентябрь, февраль), ${t.repeat_day}-го числа; срок — через ${t.due_offset_days} дн.`;
  return "Не повторяется";
}
