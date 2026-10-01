// Раньше был продублирован дословно в 6 файлах (см. TODO.md 5).
// Дата в локальном часовом поясе: toISOString() даёт UTC, и с 00:00 до 03:00
// по Москве «сегодня» превращалось во «вчера», а диапазоны дат сдвигались на день.
export function toIso(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function todayIso(): string {
  return toIso(new Date());
}

// Сервер хранит и отдаёт время в UTC, но без пометки пояса («2026-09-28T06:41:00»).
// new Date() разберёт такую строку как местное время и покажет её на часовой
// пояс раньше. Без явной пометки считаем строку UTC.
export function parseServerDateTime(iso: string): Date {
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  return new Date(hasZone ? iso : `${iso}Z`);
}

export function formatServerDateTime(iso: string): string {
  return parseServerDateTime(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
