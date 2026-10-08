import { describe, expect, it } from "vitest";
import { nextSort, sortRows } from "./tableView";

type Row = { name: string; pct: number | null };
const rows: Row[] = [
  { name: "ГД116", pct: 90 },
  { name: "ГД9", pct: null },
  { name: "ГД20", pct: 40 },
];
const getters = { name: (r: Row) => r.name, pct: (r: Row) => r.pct };

describe("nextSort", () => {
  it("по кругу: возрастание → убывание → без сортировки", () => {
    const a = nextSort(null, "name");
    expect(a).toEqual({ key: "name", dir: "asc" });
    const b = nextSort(a, "name");
    expect(b).toEqual({ key: "name", dir: "desc" });
    expect(nextSort(b, "name")).toBeNull();
    expect(nextSort(b, "pct")).toEqual({ key: "pct", dir: "asc" });
  });
});

describe("sortRows", () => {
  it("без сортировки порядок сервера", () => {
    expect(sortRows(rows, null, getters)).toBe(rows);
  });
  it("числа в названиях сравниваются по-человечески: ГД9 < ГД20 < ГД116", () => {
    expect(sortRows(rows, { key: "name", dir: "asc" }, getters).map((r) => r.name)).toEqual(["ГД9", "ГД20", "ГД116"]);
  });
  it("пустые значения всегда внизу, даже при убывании", () => {
    expect(sortRows(rows, { key: "pct", dir: "asc" }, getters).map((r) => r.pct)).toEqual([40, 90, null]);
    expect(sortRows(rows, { key: "pct", dir: "desc" }, getters).map((r) => r.pct)).toEqual([90, 40, null]);
  });
  it("исходный массив не меняется", () => {
    const copy = [...rows];
    sortRows(rows, { key: "pct", dir: "desc" }, getters);
    expect(rows).toEqual(copy);
  });
});
