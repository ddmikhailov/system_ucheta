// Тема оформления: как в системе (по умолчанию), светлая или тёмная. Выбор — удобство одного
// пользователя в этом браузере, поэтому хранится в localStorage; без него работает «как в системе».

export type ThemePref = "system" | "light" | "dark";

const KEY = "kait20_theme";

export function getThemePref(): ThemePref {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

/** Применить тему к странице: data-theme на <html> перекрывает настройку системы (см. index.css). */
export function applyTheme(pref: ThemePref): void {
  const root = document.documentElement;
  if (pref === "system") delete root.dataset.theme;
  else root.dataset.theme = pref;
}

export function setThemePref(pref: ThemePref): void {
  try {
    if (pref === "system") window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, pref);
  } catch {
    // Хранилище недоступно — тема действует до перезагрузки страницы.
  }
  applyTheme(pref);
}
