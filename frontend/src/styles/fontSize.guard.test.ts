import { describe, expect, it } from "vitest";

// Охранный тест (аудит 21.10.2026, «Телефон»): на экране 375 px текст мельче 12 px читается с трудом.
// Содержимое — от 13 px, 12 px — только второстепенные подписи; мельче — лишь значки-символы из списка ниже.
const styles = import.meta.glob("../**/*.css", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const GLYPHS = [".sort-btn__arrow"];

describe("размер шрифта", () => {
  it("в стилях нет текста мельче 12 px", () => {
    const offenders: string[] = [];
    for (const [path, text] of Object.entries(styles)) {
      for (const rule of text.split("}")) {
        const [selector = "", body = ""] = rule.split("{");
        for (const m of body.matchAll(/font-size:\s*([0-9.]+)(px|rem|em)/g)) {
          const px = m[2] === "px" ? Number(m[1]) : Number(m[1]) * 16;
          if (px < 12 && !GLYPHS.some((g) => selector.includes(g))) offenders.push(`${path}: ${selector.trim()} — ${m[0]}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
