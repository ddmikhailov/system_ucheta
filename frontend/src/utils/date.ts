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
