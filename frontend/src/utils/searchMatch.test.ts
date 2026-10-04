import { describe, expect, it } from "vitest";
import { filterByQuery, queryVariants } from "./searchMatch";

const GROUPS = ["ГД116", "ГД136", "ТИФ116", "СА172", "ИСП412д", "КСК114", "ИИ212д"];
const label = (g: string) => g;

describe("filterByQuery", () => {
  it("пустой запрос — весь список", () => {
    expect(filterByQuery(GROUPS, "  ", label)).toEqual(GROUPS);
  });

  it("кириллица: «ГД» оставляет группы, начинающиеся с ГД", () => {
    expect(filterByQuery(GROUPS, "ГД", label)).toEqual(["ГД116", "ГД136"]);
  });

  it("латиница по звучанию: «GD» → ГД, «SA» → СА", () => {
    expect(filterByQuery(GROUPS, "GD", label)).toEqual(["ГД116", "ГД136"]);
    expect(filterByQuery(GROUPS, "sa", label)).toEqual(["СА172"]);
  });

  it("забытая раскладка: «ul» на английской раскладке — это «гд»", () => {
    expect(filterByQuery(GROUPS, "ul", label)).toEqual(["ГД116", "ГД136"]);
  });

  it("регистр не важен, цифры уточняют: «гд13» → ГД136", () => {
    expect(filterByQuery(GROUPS, "гд13", label)).toEqual(["ГД136"]);
  });

  it("по началу слова: фамилия ищется и по имени, если слово внутри названия", () => {
    const people = ["Иванова Анна", "Петров Иван", "Сидорова Ирина"];
    expect(filterByQuery(people, "Анна", (p) => p)).toEqual(["Иванова Анна"]);
    expect(filterByQuery(people, "Ив", (p) => p)).toEqual(["Иванова Анна", "Петров Иван"]);
  });

  it("если по началу ничего нет — ищет внутри названия; совсем нет — пусто", () => {
    expect(filterByQuery(GROUPS, "116", label)).toEqual(["ГД116", "ТИФ116"]);
    expect(filterByQuery(GROUPS, "ЯЯЯ", label)).toEqual([]);
  });

  it("варианты запроса: исходный, по звучанию, по раскладке", () => {
    expect(queryVariants("GD")).toEqual(["gd", "гд", "пв"]);
  });
});
