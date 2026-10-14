import { describe, expect, it } from "vitest";
import { passwordRules, passwordRulesMet } from "./password";

const unmet = (pw: string) => passwordRules(pw).filter((r) => !r.ok).map((r) => r.label);

describe("passwordRules", () => {
  it("пароль со всеми классами символов проходит", () => {
    expect(passwordRulesMet("Vz8#kQm2Lp")).toBe(true);
    expect(passwordRulesMet("Тигр9Лес!Ч")).toBe(true); // кириллица считается буквами
  });

  it("перечисляет каждое невыполненное требование", () => {
    expect(unmet("short")).toEqual(["Не короче 10 символов", "Заглавная буква", "Цифра", "Спецсимвол: ! # $ % & * ?"]);
    expect(unmet("ALLUPPER12!")).toEqual(["Строчная буква"]);
    expect(unmet("NoDigitsHere!")).toEqual(["Цифра"]);
  });

  it("пробел не считается спецсимволом", () => {
    expect(unmet("Correct Horse 7")).toEqual(["Спецсимвол: ! # $ % & * ?"]);
  });
});
