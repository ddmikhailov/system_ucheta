export const TASK_STATUS_LABELS: Record<string, string> = {
  new: "Не начато",
  in_progress: "В работе",
  submitted: "На проверке",
  returned: "Возвращено",
  accepted: "Принято",
};

export const COLLECT_MODE_LABELS: Record<string, string> = {
  group: "Ответ по группе",
  student: "По каждому студенту",
  selected: "По выбранным студентам",
};

export const REVIEWER_LABELS: Record<string, string> = {
  dept_head: "Зав. отделением группы",
  edu_department: "Воспитательный отдел",
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
