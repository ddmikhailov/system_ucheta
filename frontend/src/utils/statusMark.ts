// Какой значок статуса показать назначению задачи (см. components/StatusMark).

export type MarkKind = "overdue" | "returned" | "new" | "in_progress" | "submitted" | "accepted" | "locked";

export const MARK_LABELS: Record<MarkKind, string> = {
  overdue: "Просрочено",
  returned: "Возвращено",
  new: "Не начато",
  in_progress: "В работе",
  submitted: "На проверке",
  accepted: "Принято",
  locked: "Ждёт предыдущий шаг",
};

/** Какой значок показать назначению: замок и просрочка важнее основного статуса. */
export function markKind(a: { status: string; is_overdue?: boolean; is_locked?: boolean }): MarkKind {
  if (a.is_locked) return "locked";
  if (a.status === "accepted") return "accepted";
  if (a.status === "returned") return "returned";
  if (a.is_overdue) return "overdue";
  if (a.status === "in_progress" || a.status === "submitted" || a.status === "new") return a.status;
  return "new";
}
