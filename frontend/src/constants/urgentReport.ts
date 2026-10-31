// Виды срочного сообщения заведующему (backend: schemas/students.py, UrgentReportCreate.category).
export const URGENT_CATEGORIES: Record<"misconduct" | "offense" | "emergency", string> = {
  misconduct: "Проступок",
  offense: "Правонарушение",
  emergency: "ЧП",
};
