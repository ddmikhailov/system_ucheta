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

// «2026-09-01» → «01.09.2026» (даты с сервера приходят в ISO; на экране — привычный формат).
export function formatDateRu(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

// Дата и время целиком (с годом и секундами не показываем), время с сервера — UTC без пометки пояса.
export function formatServerDateTimeFull(iso: string): string {
  return parseServerDateTime(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// «2026-10-09» → «09.10»: короткая дата там, где год очевиден (последние недели, ближайшие дни).
export function formatDayMonthRu(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}.${m}`;
}

const WEEKDAYS_SHORT = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];

// Срок с днём недели: «пт 09.10»; если год не текущий — «пт 08.01.2027», чтобы срок через Новый год не путался.
export function formatDueShort(iso: string, today: string = todayIso()): string {
  const [y, m, d] = iso.split("-").map(Number);
  const weekday = WEEKDAYS_SHORT[new Date(y, m - 1, d).getDay()];
  return iso.slice(0, 4) === today.slice(0, 4) ? `${weekday} ${formatDayMonthRu(iso)}` : `${weekday} ${formatDateRu(iso)}`;
}

// «2026-10-02» → «Пятница, 2 октября» — заголовок дня.
export function formatWeekdayLong(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const text = new Date(y, m - 1, d).toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// Местное время колледжа с сервера без пересчёта («2030-01-14T10:00:00» → «14.01 10:00»): сроки питания
// сервер отдаёт уже в местном времени, а не в UTC, как остальные метки.
export function formatLocalDateTime(iso: string): string {
  const [day, time = ""] = iso.split("T");
  return `${formatDayMonthRu(day)} ${time.slice(0, 5)}`.trim();
}

// Местное время «14:32» (например, «Сохранено в 14:32»).
export function formatTimeRu(d: Date): string {
  return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

// Сдвиг даты на n дней в ISO-формате (без часовых поясов: считаем по календарю).
export function addDaysIso(iso: string, n: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  return toIso(new Date(y, m - 1, d + n));
}

const MONTHS_NOMINATIVE = [
  "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
];

// «2026-10-02» → «Октябрь 2026» — заголовок календаря месяца.
export function formatMonthTitle(iso: string): string {
  const [y, m] = iso.split("-").map(Number);
  return `${MONTHS_NOMINATIVE[m - 1]} ${y}`;
}
