import { describe, expect, it } from "vitest";
import { formatPercent } from "./percent";

describe("formatPercent", () => {
  it("целое без дроби, дробное — с запятой, пусто — тире", () => {
    expect(formatPercent(70)).toBe("70 %");
    expect(formatPercent(86.7)).toBe("86,7 %");
    expect(formatPercent(0)).toBe("0 %");
    expect(formatPercent(null)).toBe("—");
    expect(formatPercent(undefined)).toBe("—");
  });
});
