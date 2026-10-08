// Сортировка длинных таблиц витрин: клик по заголовку — по возрастанию, второй — по убыванию, третий — как отдал сервер.

export type SortDir = "asc" | "desc";
export interface SortState<K extends string> {
  key: K;
  dir: SortDir;
}
export type SortValue = string | number | boolean | null | undefined;

export function nextSort<K extends string>(current: SortState<K> | null, key: K): SortState<K> | null {
  if (!current || current.key !== key) return { key, dir: "asc" };
  return current.dir === "asc" ? { key, dir: "desc" } : null;
}

function compare(a: string | number, b: string | number): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), "ru", { numeric: true, sensitivity: "base" });
}

/** Новый отсортированный массив. Пустые значения («—») всегда внизу, при любом направлении. */
export function sortRows<T, K extends string>(
  rows: T[],
  sort: SortState<K> | null,
  getters: Record<K, (row: T) => SortValue>,
): T[] {
  if (!sort) return rows;
  const get = getters[sort.key];
  const factor = sort.dir === "asc" ? 1 : -1;
  const normalized = (row: T): string | number | null => {
    const v = get(row);
    if (v === null || v === undefined) return null;
    return typeof v === "boolean" ? Number(v) : v;
  };
  return rows
    .map((row, index) => ({ row, index, value: normalized(row) }))
    .sort((x, y) => {
      if (x.value === null && y.value === null) return x.index - y.index;
      if (x.value === null) return 1;
      if (y.value === null) return -1;
      return factor * compare(x.value, y.value) || x.index - y.index;
    })
    .map((x) => x.row);
}
