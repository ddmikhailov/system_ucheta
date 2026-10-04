import { describe, expect, it } from "vitest";
import { plural } from "./plural";

const DAYS: [string, string, string] = ["день", "дня", "дней"];

describe("plural", () => {
  it.each([
    [0, "дней"], [1, "день"], [2, "дня"], [4, "дня"], [5, "дней"], [11, "дней"], [12, "дней"], [14, "дней"],
    [21, "день"], [22, "дня"], [25, "дней"], [101, "день"], [111, "дней"], [112, "дней"], [-1, "день"],
  ])("%i → %s", (n, form) => {
    expect(plural(n, DAYS)).toBe(form);
  });
});
