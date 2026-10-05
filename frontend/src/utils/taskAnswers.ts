import type { TaskField } from "../api/types";
import { formatDateRu } from "./date";

export type AnswerField = TaskField & { key: string };
export type Values = Record<string, unknown>;

export function isEmptyValue(value: unknown): boolean {
  return value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0);
}

/** Как на сервере (task_service.row_complete): все обязательные поля есть, а без обязательных — хоть одно значение. */
export function rowComplete(fields: AnswerField[], values: Values): boolean {
  if (fields.some((f) => f.required)) return fields.every((f) => !f.required || !isEmptyValue(values[f.key]));
  return fields.some((f) => !isEmptyValue(values[f.key]));
}

export function missingRequired(fields: AnswerField[], values: Values): string[] {
  return fields.filter((f) => f.required && isEmptyValue(values[f.key])).map((f) => f.label);
}

/** Проверка до сохранения — те же правила, что на сервере, чтобы автосохранение не спорило
 * с куратором, пока он ещё набирает ссылку или число. null — значение подходит. */
export function localProblem(field: AnswerField, value: unknown): string | null {
  if (isEmptyValue(value)) return null;
  if (field.type === "link") {
    const text = String(value).trim();
    return /^https?:\/\/\S+$/.test(text) && text.length <= 500 ? null : "нужна ссылка вида https://…";
  }
  if (field.type === "number") return Number.isFinite(Number(String(value).replace(",", "."))) ? null : "нужно число";
  if (field.type === "text" && String(value).length > 2000) return "слишком длинный текст (максимум 2000 символов)";
  return null;
}

/** Значение для чтения (проверяющий, отправленный ответ). */
export function valueText(field: AnswerField, value: unknown): string {
  if (isEmptyValue(value)) return "—";
  if (field.type === "bool") return value === true ? "да" : "нет";
  if (field.type === "date" && typeof value === "string") return formatDateRu(value);
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

/** «Иванова Анна Ивановна» → «ИА». */
export function initials(fullName: string): string {
  return fullName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}
