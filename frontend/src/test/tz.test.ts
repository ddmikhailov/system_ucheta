import { expect, it } from "vitest";

it("тесты идут в часовом поясе колледжа (UTC+3)", () => {
  expect(new Date(2026, 9, 1).getTimezoneOffset()).toBe(-180);
});
