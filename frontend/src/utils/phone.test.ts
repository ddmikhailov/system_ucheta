import { describe, expect, it } from "vitest";
import { telHref } from "./phone";

describe("telHref", () => {
  it("оставляет цифры и ведущий плюс", () => {
    expect(telHref("+7 (900) 123-45-67")).toBe("tel:+79001234567");
    expect(telHref("8 900 123 45 67")).toBe("tel:89001234567");
    expect(telHref("  +7900 1234567 ")).toBe("tel:+79001234567");
  });

  it("слишком короткое и пустое — не номер", () => {
    expect(telHref("1-2-3")).toBeNull();
    expect(telHref("")).toBeNull();
    expect(telHref(null)).toBeNull();
    expect(telHref(undefined)).toBeNull();
    expect(telHref("нет телефона")).toBeNull();
  });
});
