import { describe, expect, it } from "vitest";
import { formatDateRu, formatServerDateTimeFull, parseServerDateTime, toIso } from "./date";

describe("toIso", () => {
  it("форматирует локальную дату без сдвига в UTC", () => {
    // Полночь по местному времени: toISOString() в поясе восточнее UTC дал бы предыдущий день.
    expect(toIso(new Date(2026, 9, 1, 0, 5))).toBe("2026-10-01");
    expect(toIso(new Date(2026, 0, 9))).toBe("2026-01-09");
  });
});

describe("formatDateRu", () => {
  it("переводит ISO в ДД.ММ.ГГГГ", () => {
    expect(formatDateRu("2026-09-01")).toBe("01.09.2026");
  });
});

describe("parseServerDateTime", () => {
  it("строку без пометки пояса считает UTC", () => {
    expect(parseServerDateTime("2026-09-28T06:41:00").toISOString()).toBe("2026-09-28T06:41:00.000Z");
  });

  it("не трогает строку с явным поясом", () => {
    expect(parseServerDateTime("2026-09-28T06:41:00+03:00").toISOString()).toBe("2026-09-28T03:41:00.000Z");
    expect(parseServerDateTime("2026-09-28T06:41:00Z").toISOString()).toBe("2026-09-28T06:41:00.000Z");
  });
});

describe("formatServerDateTimeFull", () => {
  it("показывает дату с годом и время", () => {
    expect(formatServerDateTimeFull("2026-09-28T06:41:00Z")).toMatch(/28\.09\.2026/);
  });
});
