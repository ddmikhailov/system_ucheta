import { plural } from "./plural";
import { todayIso } from "./date";

const DAYS: [string, string, string] = ["день", "дня", "дней"];

function toUtcDay(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  return Date.UTC(y, m - 1, d) / 86_400_000;
}

/** Сколько календарных дней до даты (отрицательное — дата прошла). */
export function daysUntil(iso: string, today: string = todayIso()): number {
  return Math.round(toUtcDay(iso) - toUtcDay(today));
}

/** Срок словами: «сегодня», «завтра», «через 5 дней», «просрочено на 2 дня». */
export function relativeDue(iso: string, today: string = todayIso()): string {
  const days = daysUntil(iso, today);
  if (days === 0) return "сегодня";
  if (days === 1) return "завтра";
  if (days > 1) return `через ${days} ${plural(days, DAYS)}`;
  return `просрочено на ${-days} ${plural(-days, DAYS)}`;
}
