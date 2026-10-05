import { describe, expect, it } from "vitest";
import { initials, localProblem, missingRequired, rowComplete, valueText } from "./taskAnswers";
import type { AnswerField } from "./taskAnswers";

const f = (over: Partial<AnswerField>): AnswerField => ({ key: "k", label: "Поле", type: "text", required: false, options: [], ...over });

describe("taskAnswers", () => {
  it("rowComplete: обязательные поля решают; без обязательных — хоть одно значение", () => {
    const withRequired = [f({ key: "a", required: true }), f({ key: "b", type: "multiselect" })];
    expect(rowComplete(withRequired, { b: ["x"] })).toBe(false);
    expect(rowComplete(withRequired, { a: "есть" })).toBe(true);

    const optional = [f({ key: "a", type: "multiselect" }), f({ key: "b", type: "bool" })];
    expect(rowComplete(optional, { a: [] })).toBe(false);
    expect(rowComplete(optional, { b: false })).toBe(true);
  });

  it("missingRequired — подписи пустых обязательных полей", () => {
    const fields = [f({ key: "a", label: "Телефон", required: true }), f({ key: "b", label: "Почта", required: true })];
    expect(missingRequired(fields, { a: "+7", b: "" })).toEqual(["Почта"]);
  });

  it("localProblem: ссылка и число как на сервере, пустое — не ошибка", () => {
    expect(localProblem(f({ type: "link" }), "vk.com")).toBe("нужна ссылка вида https://…");
    expect(localProblem(f({ type: "link" }), "https://vk.com/v")).toBeNull();
    expect(localProblem(f({ type: "number" }), "12,5")).toBeNull();
    expect(localProblem(f({ type: "number" }), "много")).toBe("нужно число");
    expect(localProblem(f({ type: "link" }), "")).toBeNull();
    expect(localProblem(f({ type: "text" }), "я".repeat(2001))).toMatch(/слишком длинный/);
  });

  it("valueText — для чтения", () => {
    expect(valueText(f({ type: "bool" }), true)).toBe("да");
    expect(valueText(f({ type: "bool" }), false)).toBe("нет");
    expect(valueText(f({ type: "date" }), "2026-10-09")).toBe("09.10.2026");
    expect(valueText(f({ type: "multiselect" }), ["Спорт", "Танцы"])).toBe("Спорт, Танцы");
    expect(valueText(f({}), null)).toBe("—");
  });

  it("initials — две буквы из ФИО", () => {
    expect(initials("Иванова Анна Ивановна")).toBe("ИА");
    expect(initials("  петров  ")).toBe("П");
  });
});
