// Память переходов в пределах вкладки браузера (sessionStorage): откуда пришли на каждую запись
// истории, где была прокрутка и с какими параметрами пользователь ушёл с вкладки страницы.
// Переживает обновление страницы, но не выход: logout очищает всё (clearNavMemory).

const PREFIX = "nav:";
const PREV_KEY = `${PREFIX}prev`;
const SCROLL_KEY = `${PREFIX}scroll`;
const TABS_PREFIX = `${PREFIX}tab:`;
const STATE_KEY = `${PREFIX}state`;
/** Сколько последних записей истории помнить — чтобы sessionStorage не рос бесконечно. */
const LIMIT = 200;

/** Страницы, на которые «Назад» в интерфейсе не возвращает. */
const NOT_A_BACK_TARGET = ["/login", "/change-password"];

type StringMap = Record<string, string>;
type NumberMap = Record<string, number>;

function readMap<T>(key: string): Record<string, T> {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as Record<string, T>) : {};
  } catch {
    return {};
  }
}

function writeMap<T>(key: string, map: Record<string, T>): void {
  const keys = Object.keys(map);
  if (keys.length > LIMIT) for (const k of keys.slice(0, keys.length - LIMIT)) delete map[k];
  try {
    sessionStorage.setItem(key, JSON.stringify(map));
  } catch {
    // Приватный режим или переполнение — без памяти просто работают запасные адреса.
  }
}

// Кнопки «Назад» рисуются раньше, чем NavMemory запишет, откуда пришли, — подписка их перерисует.
const listeners = new Set<() => void>();
export function subscribeNavMemory(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
function notify(): void {
  for (const listener of listeners) listener();
}

/** Адрес, с которого пришли на запись истории `entryKey`, или null (открыли напрямую, по закладке). */
export function previousUrl(entryKey: string): string | null {
  return readMap<string>(PREV_KEY)[entryKey] ?? null;
}

export function setPreviousUrl(entryKey: string, url: string | null): void {
  const map = readMap<string>(PREV_KEY) as StringMap;
  const path = url?.split("?")[0] ?? "";
  if (url === null || NOT_A_BACK_TARGET.includes(path) || path === "/") delete map[entryKey];
  else map[entryKey] = url;
  writeMap(PREV_KEY, map);
  notify();
}

export function savedScroll(entryKey: string): number | null {
  return readMap<number>(SCROLL_KEY)[entryKey] ?? null;
}

export function saveScroll(entryKey: string, y: number): void {
  const map = readMap<number>(SCROLL_KEY) as NumberMap;
  map[entryKey] = Math.round(y);
  writeMap(SCROLL_KEY, map);
}

type EntryState = Record<string, unknown>;

/** Состояние экрана, привязанное к записи истории (фильтры, сортировка, выбранный день витрин):
 * браузерная «Назад» и обновление страницы возвращают его, новый переход в раздел начинается заново. */
export function entryState(entryKey: string): EntryState {
  return readMap<EntryState>(STATE_KEY)[entryKey] ?? {};
}

export function setEntryStateValue(entryKey: string, name: string, value: unknown): void {
  const map = readMap<EntryState>(STATE_KEY);
  map[entryKey] = { ...(map[entryKey] ?? {}), [name]: value };
  writeMap(STATE_KEY, map);
}

/** Запись истории заменили (сменились параметры адреса) — состояние экрана переезжает на новую. */
export function moveEntryState(fromKey: string, toKey: string): void {
  const map = readMap<EntryState>(STATE_KEY);
  if (!map[fromKey]) return;
  map[toKey] = { ...map[fromKey], ...(map[toKey] ?? {}) };
  delete map[fromKey];
  writeMap(STATE_KEY, map);
}

/** Параметры адреса, с которыми пользователь ушёл со вкладки `tab` страницы `scope`. */
export function savedTabSearch(scope: string, tab: string): string | null {
  try {
    return sessionStorage.getItem(`${TABS_PREFIX}${scope}:${tab}`);
  } catch {
    return null;
  }
}

export function saveTabSearch(scope: string, tab: string, search: string): void {
  try {
    sessionStorage.setItem(`${TABS_PREFIX}${scope}:${tab}`, search);
  } catch {
    // см. writeMap
  }
}

/** Выход из платформы: следующий пользователь начинает с главного экрана и чистой памятью. */
export function clearNavMemory(): void {
  try {
    for (let i = sessionStorage.length - 1; i >= 0; i--) {
      const key = sessionStorage.key(i);
      if (key?.startsWith(PREFIX)) sessionStorage.removeItem(key);
    }
    notify();
  } catch {
    // нечего чистить
  }
}
