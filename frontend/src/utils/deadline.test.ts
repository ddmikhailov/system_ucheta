import { describe, expect, it } from "vitest";
import { formatDueShort } from "./date";
import { daysUntil, relativeDue } from "./deadline";

describe("deadline", () => {
  it("daysUntil считает календарные дни, через границу месяца и года", () => {
    expect(daysUntil("2026-10-09", "2026-10-04")).toBe(5);
    expect(daysUntil("2026-11-01", "2026-10-31")).toBe(1);
    expect(daysUntil("2027-01-01", "2026-12-31")).toBe(1);
    expect(daysUntil("2026-10-02", "2026-10-04")).toBe(-2);
  });

  it("переход на летнее/зимнее время не сбивает счёт", () => {
    expect(daysUntil("2026-03-30", "2026-03-28")).toBe(2);
    expect(daysUntil("2026-10-26", "2026-10-24")).toBe(2);
  });

  it("relativeDue — словами и со склонением", () => {
    expect(relativeDue("2026-10-04", "2026-10-04")).toBe("сегодня");
    expect(relativeDue("2026-10-05", "2026-10-04")).toBe("завтра");
    expect(relativeDue("2026-10-06", "2026-10-04")).toBe("через 2 дня");
    expect(relativeDue("2026-10-25", "2026-10-04")).toBe("через 21 день");
    expect(relativeDue("2026-10-03", "2026-10-04")).toBe("просрочено на 1 день");
    expect(relativeDue("2026-09-29", "2026-10-04")).toBe("просрочено на 5 дней");
  });

  it("formatDueShort — день недели и дата; год — только если он не текущий", () => {
    expect(formatDueShort("2026-10-09", "2026-10-04")).toBe("пт 09.10");
    expect(formatDueShort("2026-10-04", "2026-10-04")).toBe("вс 04.10");
    expect(formatDueShort("2027-01-08", "2026-12-28")).toBe("пт 08.01.2027");
  });
});
