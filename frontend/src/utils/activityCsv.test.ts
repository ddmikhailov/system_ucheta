import { describe, expect, it } from "vitest";
import { activityCsv } from "./activityCsv";

describe("activityCsv", () => {
  it("BOM, «;», подписи действий и кавычки внутри значений", () => {
    const csv = activityCsv([
      { id: 1, action: "day.submit", entity_type: "study_group_day", entity_id: '5:"2026-10-05"', created_at: "2026-10-05T07:00:00" },
    ]);
    expect(csv.startsWith("﻿")).toBe(true);
    const [header, row] = csv.slice(1).split("\r\n");
    expect(header).toBe('"Когда";"Действие";"Объект";"Номер объекта"');
    expect(row).toContain('"Сдал(а) день"');
    expect(row).toContain('"5:""2026-10-05"""');
  });
});
