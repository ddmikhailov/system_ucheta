import { describe, expect, it } from "vitest";

// Охранный тест: длинные поля — только через общий TextArea (без ручного растягивания, с кнопкой «Развернуть на весь экран»).
const sources = import.meta.glob("../**/*.tsx", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const styles = import.meta.glob("../**/*.css", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

describe("длинные поля", () => {
  it("«голых» <textarea> нет нигде, кроме самого TextArea", () => {
    const offenders = Object.entries(sources)
      .filter(([path]) => !path.endsWith(".test.tsx") && !path.endsWith("/TextArea.tsx"))
      .filter(([, text]) => /<textarea[\s>]/.test(text))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });

  it("в стилях нигде не разрешено растягивать поле мышью", () => {
    const offenders = Object.entries(styles)
      .filter(([, text]) => /resize:\s*(vertical|horizontal|both)/.test(text))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });
});
