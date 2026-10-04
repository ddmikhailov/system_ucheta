import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  SUMMARY_PRESETS,
  buildSummaryLink,
  defaultSummaryFilters,
  filtersFromParams,
  filtersToParams,
  initialSummaryFilters,
  loadSavedFilters,
  sanitizeSummaryFilters,
  saveFilters,
  summaryExportParams,
} from "./summaryFilters";

// Четверг, 15 октября 2026, полдень по местному времени (часовой пояс тестов — Москва).
beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2026, 9, 15, 12, 0, 0));
});
afterEach(() => vi.useRealTimers());

const params = (s: string) => new URLSearchParams(s);

describe("быстрые периоды", () => {
  const range = (key: string) => SUMMARY_PRESETS.find((p) => p.key === key)!.range();

  it("считаются от сегодняшнего дня", () => {
    expect(range("today")).toEqual(["2026-10-15", "2026-10-15"]);
    expect(range("yesterday")).toEqual(["2026-10-14", "2026-10-14"]);
    expect(range("7d")).toEqual(["2026-10-09", "2026-10-15"]);
    expect(range("month")).toEqual(["2026-10-01", "2026-10-15"]);
    expect(range("prev-month")).toEqual(["2026-09-01", "2026-09-30"]);
  });

  it("прошлый месяц на стыке года и в високосный февраль", () => {
    vi.setSystemTime(new Date(2027, 0, 5, 12));
    expect(range("prev-month")).toEqual(["2026-12-01", "2026-12-31"]);
    vi.setSystemTime(new Date(2028, 2, 10, 12));
    expect(range("prev-month")).toEqual(["2028-02-01", "2028-02-29"]);
  });
});

describe("умолчания и выгрузка", () => {
  it("по умолчанию: последние 14 дней, всё отделение, пара 1, «всего и к паре», порог 90", () => {
    expect(defaultSummaryFilters()).toMatchObject({
      dateFrom: "2026-10-01", dateTo: "2026-10-15", departmentId: "all", course: "all", groupId: "all",
      pair: 1, slice: "both", hideEmpty: true, onlyProblems: false, threshold: 90, view: "daily",
    });
  });

  it("выгрузка Excel берёт период, пару и отбор; отделение — только если роль вправе его выбирать", () => {
    const f = { ...defaultSummaryFilters(), departmentId: 3, course: 2, groupId: 9, pair: 4 };
    expect(summaryExportParams(f, true)).toBe("date_from=2026-10-01&date_to=2026-10-15&pair=4&department_id=3&course=2&study_group_id=9");
    expect(summaryExportParams(f, false)).toBe("date_from=2026-10-01&date_to=2026-10-15&pair=4&course=2&study_group_id=9");
    expect(summaryExportParams(defaultSummaryFilters(), true)).toBe("date_from=2026-10-01&date_to=2026-10-15&pair=1");
  });
});

describe("фильтры ↔ адрес", () => {
  it("в адрес попадает только отличное от умолчаний", () => {
    const p = filtersToParams(defaultSummaryFilters(), false);
    expect(p.toString()).toBe("from=2026-10-01&to=2026-10-15");
    const f = { ...defaultSummaryFilters(), course: 3, onlyProblems: true, hideEmpty: false, hiddenCodes: ["о", "н"], view: "groups" as const, threshold: 80, slice: "pair" as const, pair: 2 };
    const q = filtersToParams(f, false);
    expect(Object.fromEntries(q)).toEqual({
      from: "2026-10-01", to: "2026-10-15", course: "3", pair: "2", slice: "pair", hide: "о,н", problems: "1", thr: "80", empty: "0", view: "groups",
    });
  });

  it("для запоминания быстрый период пишется ключом, для ссылки — конкретными датами", () => {
    const f = { ...defaultSummaryFilters(), preset: "7d", dateFrom: "2026-10-09", dateTo: "2026-10-15" };
    expect(filtersToParams(f, true).get("period")).toBe("7d");
    expect(filtersToParams(f, true).has("from")).toBe(false);
    expect(filtersToParams(f, false).get("from")).toBe("2026-10-09");
    expect(filtersToParams(f, false).has("period")).toBe(false);
  });

  it("круговой путь сохраняет все фильтры", () => {
    const f = { ...defaultSummaryFilters(), departmentId: 2, course: 1, groupId: 5, pair: 3, slice: "all" as const, hiddenCodes: ["б"], onlyProblems: true, threshold: 75, hideEmpty: false, view: "period" as const };
    expect(filtersFromParams(filtersToParams(f, false))).toEqual(f);
  });

  it("запомненный «7 дней» завтра означает снова последние 7 дней", () => {
    const saved = filtersToParams({ ...defaultSummaryFilters(), preset: "7d" }, true);
    vi.setSystemTime(new Date(2026, 9, 20, 12));
    const restored = filtersFromParams(saved)!;
    expect([restored.dateFrom, restored.dateTo]).toEqual(["2026-10-14", "2026-10-20"]);
    expect(restored.preset).toBe("7d");
  });

  it("без фильтров в адресе — null (применяются сохранённые или умолчания)", () => {
    expect(filtersFromParams(params("tab=summary"))).toBeNull();
    expect(filtersFromParams(params(""))).toBeNull();
  });
});

describe("ссылке нельзя доверять слепо", () => {
  it("мусор и выход за границы заменяются умолчаниями", () => {
    const f = filtersFromParams(params("from=вчера&to=2026-13&dept=-1&course=99&group=abc&pair=0&slice=evil&thr=500&view=hack&hide=о,<script>,ж"))!;
    const d = defaultSummaryFilters();
    expect([f.dateFrom, f.dateTo]).toEqual([d.dateFrom, d.dateTo]);
    expect([f.departmentId, f.course, f.groupId, f.pair, f.slice, f.threshold, f.view]).toEqual(["all", "all", "all", 1, "both", 90, "daily"]);
    expect(f.hiddenCodes).toEqual(["о", "ж"]); // «<script>» и прочее не код отметки
  });

  it("допустимые границы принимаются", () => {
    const f = filtersFromParams(params("course=6&pair=10&thr=100&dept=1&group=1000000"))!;
    expect([f.course, f.pair, f.threshold, f.departmentId, f.groupId]).toEqual([6, 10, 100, 1, 1000000]);
  });

  it("скрытых кодов не больше 20", () => {
    const codes = Array.from({ length: 30 }, (_, i) => String.fromCharCode(1072 + (i % 30))).join(",");
    expect(filtersFromParams(params(`hide=${codes}`))!.hiddenCodes).toHaveLength(20);
  });

  it("неизвестный быстрый период не ломает даты", () => {
    const f = filtersFromParams(params("period=forever&from=2026-09-01&to=2026-09-30"))!;
    expect([f.dateFrom, f.dateTo, f.preset]).toEqual(["2026-09-01", "2026-09-30", null]);
  });
});

describe("sanitizeSummaryFilters", () => {
  const base = { ...defaultSummaryFilters(), departmentId: 2, groupId: 7 };

  it("роль без выбора отделения теряет отделение; несуществующая группа сбрасывается", () => {
    expect(sanitizeSummaryFilters(base, [{ id: 7 }], false)).toMatchObject({ departmentId: "all", groupId: 7 });
    expect(sanitizeSummaryFilters(base, [{ id: 1 }], true)).toMatchObject({ departmentId: 2, groupId: "all" });
    expect(sanitizeSummaryFilters(base, [{ id: 1 }], false)).toMatchObject({ departmentId: "all", groupId: "all" });
  });

  it("пока группы не загружены, фильтр не трогается; допустимое остаётся тем же объектом", () => {
    expect(sanitizeSummaryFilters(base, [], true)).toBe(base);
    expect(sanitizeSummaryFilters(base, [{ id: 7 }], true)).toBe(base);
  });
});

describe("запоминание и ссылка", () => {
  it("сохранённое восстанавливается; ссылка из адреса важнее сохранённого", () => {
    saveFilters({ ...defaultSummaryFilters(), course: 2, view: "groups" });
    expect(loadSavedFilters()).toMatchObject({ course: 2, view: "groups" });
    expect(initialSummaryFilters(params(""))).toMatchObject({ course: 2 });
    expect(initialSummaryFilters(params("course=4"))).toMatchObject({ course: 4, view: "daily" });
  });

  it("без сохранённого и без ссылки — умолчания", () => {
    expect(initialSummaryFilters(params(""))).toEqual(defaultSummaryFilters());
  });

  it("недоступное или испорченное хранилище не ломает работу", () => {
    const original = Storage.prototype.getItem;
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("заблокировано");
    });
    expect(loadSavedFilters()).toBeNull();
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("нет места");
    });
    expect(() => saveFilters(defaultSummaryFilters())).not.toThrow();
    Storage.prototype.getItem = original;
  });

  it("ссылка открывает «Свод» с конкретными датами", () => {
    const link = new URL(buildSummaryLink({ ...defaultSummaryFilters(), preset: "7d", course: 2 }));
    expect(link.pathname).toBe("/dashboards");
    expect(Object.fromEntries(link.searchParams)).toMatchObject({ tab: "summary", from: "2026-10-01", to: "2026-10-15", course: "2" });
    expect(link.searchParams.has("period")).toBe(false);
  });
});
