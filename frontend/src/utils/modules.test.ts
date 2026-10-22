import { describe, expect, it } from "vitest";
import { MODULE } from "../constants/modules";
import type { ModuleName } from "../constants/modules";
import { makeUser } from "../test/utils";
import { isModuleOn } from "./modules";

// Урезанный набор без досье и индивидуальной работы (режим настраиваемый; релизный набор их включает).
const RELEASE_MODULES: readonly ModuleName[] = ["attendance", "tasks", "my_id", "meals"];

describe("isModuleOn", () => {
  it("включён, если есть в списке сервера", () => {
    const user = makeUser("admin", { modules: [...RELEASE_MODULES] });
    expect(isModuleOn(user, MODULE.MEALS)).toBe(true);
    expect(isModuleOn(user, MODULE.ATTENDANCE)).toBe(true);
  });

  it("выключен, если сервер его не перечислил", () => {
    const user = makeUser("admin", { modules: [...RELEASE_MODULES] });
    for (const name of [MODULE.DOSSIER, MODULE.PASSPORT, MODULE.INDIVIDUAL_WORK, MODULE.PLAN, MODULE.MEETINGS, MODULE.REPORTS]) {
      expect(isModuleOn(user, name)).toBe(false);
    }
  });

  it("без поля modules считается, что включено всё; без пользователя — ничего", () => {
    expect(isModuleOn(makeUser("admin"), MODULE.PASSPORT)).toBe(true);
    expect(isModuleOn(null, MODULE.ATTENDANCE)).toBe(false);
  });
});
