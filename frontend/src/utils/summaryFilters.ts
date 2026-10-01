import { toIso, todayIso } from "./date";

export type SliceMode = "both" | "all" | "pair";
export type SummaryView = "daily" | "period" | "groups";

export interface SummaryFilters {
  dateFrom: string;
  dateTo: string;
  // Ключ быстрого периода («7d», «month»…) или null, если даты введены вручную.
  // Нужен, чтобы запомненный «7 дней» завтра снова означал «последние 7 дней»,
  // а не конкретные вчерашние даты.
  preset: string | null;
  departmentId: number | "all";
  course: number | "all";
  groupId: number | "all";
  pair: number;
  slice: SliceMode;
  hiddenCodes: string[];
  onlyProblems: boolean;
  threshold: number;
  hideEmpty: boolean;
  view: SummaryView;
}

export function daysAgoIso(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return toIso(d);
}

function monthStartIso(offset: number): string {
  const now = new Date();
  return toIso(new Date(now.getFullYear(), now.getMonth() + offset, 1));
}

function monthEndIso(offset: number): string {
  const now = new Date();
  return toIso(new Date(now.getFullYear(), now.getMonth() + offset + 1, 0));
}

export const SUMMARY_PRESETS: { key: string; label: string; range: () => [string, string] }[] = [
  { key: "today", label: "Сегодня", range: () => [todayIso(), todayIso()] },
  { key: "yesterday", label: "Вчера", range: () => [daysAgoIso(1), daysAgoIso(1)] },
  { key: "7d", label: "7 дней", range: () => [daysAgoIso(6), todayIso()] },
  { key: "month", label: "Этот месяц", range: () => [monthStartIso(0), todayIso()] },
  { key: "prev-month", label: "Прошлый месяц", range: () => [monthStartIso(-1), monthEndIso(-1)] },
];

export function defaultSummaryFilters(): SummaryFilters {
  return {
    dateFrom: daysAgoIso(14),
    dateTo: todayIso(),
    preset: null,
    departmentId: "all",
    course: "all",
    groupId: "all",
    pair: 1,
    slice: "both",
    hiddenCodes: [],
    onlyProblems: false,
    threshold: 90,
    hideEmpty: true,
    view: "daily",
  };
}

/** Параметры выгрузки Excel: те же период, отделение, курс, группа и пара, что
 * выбраны на экране (столбцы, пороги и сортировка действуют только на экране). */
export function summaryExportParams(f: SummaryFilters, canFilterDepartment: boolean): string {
  const parts = [`date_from=${f.dateFrom}`, `date_to=${f.dateTo}`, `pair=${f.pair}`];
  if (canFilterDepartment && f.departmentId !== "all") parts.push(`department_id=${f.departmentId}`);
  if (f.course !== "all") parts.push(`course=${f.course}`);
  if (f.groupId !== "all") parts.push(`study_group_id=${f.groupId}`);
  return parts.join("&");
}

// ---- ссылка и запоминание ----

const FILTER_KEYS = [
  "from", "to", "period", "dept", "course", "group", "pair", "slice", "hide", "problems", "thr", "empty", "view",
];

/** Фильтры → параметры адресной строки (только отличающиеся от умолчаний).
 * relative=true: быстрый период пишется ключом («period=7d»), а не датами —
 * так запоминается выбор; для ссылки даты всегда конкретные, чтобы она
 * открывалась ровно с тем, что видел отправитель. */
export function filtersToParams(f: SummaryFilters, relative: boolean): URLSearchParams {
  const defaults = defaultSummaryFilters();
  const p = new URLSearchParams();
  if (relative && f.preset) {
    p.set("period", f.preset);
  } else {
    p.set("from", f.dateFrom);
    p.set("to", f.dateTo);
  }
  if (f.departmentId !== "all") p.set("dept", String(f.departmentId));
  if (f.course !== "all") p.set("course", String(f.course));
  if (f.groupId !== "all") p.set("group", String(f.groupId));
  if (f.pair !== defaults.pair) p.set("pair", String(f.pair));
  if (f.slice !== defaults.slice) p.set("slice", f.slice);
  if (f.hiddenCodes.length > 0) p.set("hide", f.hiddenCodes.join(","));
  if (f.onlyProblems) p.set("problems", "1");
  if (f.threshold !== defaults.threshold) p.set("thr", String(f.threshold));
  if (!f.hideEmpty) p.set("empty", "0");
  if (f.view !== defaults.view) p.set("view", f.view);
  return p;
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function intInRange(raw: string | null, min: number, max: number): number | null {
  if (raw === null || !/^\d+$/.test(raw)) return null;
  const n = Number(raw);
  return n >= min && n <= max ? n : null;
}

/** Параметры → фильтры. null, если в параметрах нет ни одного фильтра
 * (например, открыли просто /dashboards?tab=summary). Всё непонятное
 * отбрасывается и заменяется умолчанием — ссылке нельзя доверять слепо. */
export function filtersFromParams(p: URLSearchParams): SummaryFilters | null {
  if (!FILTER_KEYS.some((k) => p.has(k))) return null;
  const f = defaultSummaryFilters();

  const preset = SUMMARY_PRESETS.find((x) => x.key === p.get("period"));
  const from = p.get("from");
  const to = p.get("to");
  if (preset) {
    [f.dateFrom, f.dateTo] = preset.range();
    f.preset = preset.key;
  } else if (from && to && ISO_DATE.test(from) && ISO_DATE.test(to)) {
    f.dateFrom = from;
    f.dateTo = to;
  }

  const dept = intInRange(p.get("dept"), 1, 1_000_000);
  if (dept !== null) f.departmentId = dept;
  const course = intInRange(p.get("course"), 1, 6);
  if (course !== null) f.course = course;
  const group = intInRange(p.get("group"), 1, 1_000_000);
  if (group !== null) f.groupId = group;
  const pair = intInRange(p.get("pair"), 1, 10);
  if (pair !== null) f.pair = pair;
  const slice = p.get("slice");
  if (slice === "all" || slice === "pair" || slice === "both") f.slice = slice;
  const hide = p.get("hide");
  if (hide) {
    f.hiddenCodes = hide
      .split(",")
      .filter((c) => /^[\p{L}]{1,4}$/u.test(c))
      .slice(0, 20);
  }
  f.onlyProblems = p.get("problems") === "1";
  const threshold = intInRange(p.get("thr"), 1, 100);
  if (threshold !== null) f.threshold = threshold;
  if (p.get("empty") === "0") f.hideEmpty = false;
  const view = p.get("view");
  if (view === "daily" || view === "period" || view === "groups") f.view = view;
  return f;
}

/** Приводит фильтры в соответствие с тем, что реально доступно: роль без
 * выбора отделения его не имеет, а удалённой/чужой группы нет в списке. */
export function sanitizeSummaryFilters(
  f: SummaryFilters,
  groups: { id: number }[],
  canFilterDepartment: boolean,
): SummaryFilters {
  const groupMissing = f.groupId !== "all" && groups.length > 0 && !groups.some((g) => g.id === f.groupId);
  const departmentNotAllowed = f.departmentId !== "all" && !canFilterDepartment;
  if (!groupMissing && !departmentNotAllowed) return f;
  return {
    ...f,
    groupId: groupMissing ? "all" : f.groupId,
    departmentId: departmentNotAllowed ? "all" : f.departmentId,
  };
}

/** Ссылка, которая открывает «Свод» ровно с этими фильтрами. */
export function buildSummaryLink(f: SummaryFilters): string {
  const p = filtersToParams(f, false);
  p.set("tab", "summary");
  return `${window.location.origin}/dashboards?${p.toString()}`;
}

const STORAGE_KEY = "kait20_summary_filters_v1";

export function loadSavedFilters(): SummaryFilters | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? filtersFromParams(new URLSearchParams(raw)) : null;
  } catch {
    return null; // приватное окно/заблокированное хранилище — работаем без запоминания
  }
}

export function saveFilters(f: SummaryFilters): void {
  try {
    localStorage.setItem(STORAGE_KEY, filtersToParams(f, true).toString());
  } catch {
    // нет места/хранилище недоступно — выбор просто не запомнится
  }
}

/** Начальные фильтры: из ссылки, иначе последний сохранённый выбор, иначе умолчания. */
export function initialSummaryFilters(search: URLSearchParams): SummaryFilters {
  return filtersFromParams(search) ?? loadSavedFilters() ?? defaultSummaryFilters();
}
