import { describe, expect, it } from "vitest";
import { clientContext, describeBrowser } from "./clientInfo";

describe("describeBrowser", () => {
  it.each([
    ["Mozilla/5.0 (Linux; Android 14; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36", "Chrome 141 · Android"],
    ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 YaBrowser/25.8.0.0 Safari/537.36", "Яндекс Браузер 25 · Windows"],
    ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0", "Edge 141 · Windows"],
    ["Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0", "Firefox 140 · Linux"],
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1", "Safari 18 · iOS"],
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Safari/605.1.15", "Safari 18 · macOS"],
  ])("%s → %s", (ua, expected) => {
    expect(describeBrowser(ua)).toBe(expected);
  });

  it("незнакомый браузер — начало строки как есть, не длиннее 120 символов", () => {
    expect(describeBrowser("x".repeat(300))).toBe("x".repeat(120));
  });
});

describe("clientContext", () => {
  it("берёт только путь страницы, без параметров", () => {
    window.history.pushState({}, "", "/students?q=Петров");
    expect(clientContext("3.6.0")).toMatchObject({ page: "/students", version: "3.6.0" });
  });
});
