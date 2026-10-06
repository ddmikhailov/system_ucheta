import type { UserAdmin } from "../api/types";

/** Состояние учётной записи одним словом — для списка пользователей и профиля. */
export function userStatusLabel(u: UserAdmin): string {
  if (!u.is_active) return "в архиве";
  if (u.is_locked) return "заблокирован";
  if (!u.has_password) return "нет пароля";
  if (u.must_change_password) return "ждёт смены пароля";
  return "активен";
}
