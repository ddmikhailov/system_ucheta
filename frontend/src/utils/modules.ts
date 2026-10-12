import type { MeResponse } from "../api/types";
import type { ModuleName } from "../constants/modules";

/** Включён ли модуль платформы для этого пользователя. Сервер всегда отдаёт `modules`; если поля нет
 * (старый ответ или заглушка в тесте) — считаем, что включено всё. Без пользователя — выключено. */
export function isModuleOn(user: MeResponse | null | undefined, name: ModuleName): boolean {
  if (!user) return false;
  return user.modules === undefined || user.modules.includes(name);
}
