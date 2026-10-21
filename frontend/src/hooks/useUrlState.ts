import { useCallback, useLayoutEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { SortDir, SortState } from "../utils/tableView";

type Patch = Record<string, string | null>;
/** Как у useState: новое значение или функция от текущего. */
type Update<T> = T | ((prev: T) => T);

// Последний известный адрес, общий для всех хуков: несколько вызовов подряд в одном обработчике
// («Сбросить фильтры») складываются, а не затирают друг друга снимком из рендера.
let latestSearch = "";

/** Меняет параметры адреса без новой записи в истории. */
export function usePatchSearch(): (patch: Patch) => void {
  const navigate = useNavigate();
  const location = useLocation();
  useLayoutEffect(() => {
    latestSearch = location.search;
  }, [location.search]);
  const state: unknown = location.state;
  return useCallback(
    (patch: Patch) => {
      const next = new URLSearchParams(latestSearch);
      for (const [key, value] of Object.entries(patch)) {
        if (value === null) next.delete(key);
        else next.set(key, value);
      }
      const search = next.toString() ? `?${next.toString()}` : "";
      if (search === latestSearch) return;
      latestSearch = search;
      navigate({ search: latestSearch }, { replace: true, state });
    },
    [navigate, state]
  );
}

/** Строковое состояние экрана (поиск, фильтр) в адресе: «Назад», обновление страницы и ссылка
 * возвращают его на место. Значение по умолчанию в адрес не пишется. */
export function useUrlParam(name: string, fallback = ""): [string, (next: string) => void] {
  const { search } = useLocation();
  const patch = usePatchSearch();
  const value = new URLSearchParams(search).get(name) ?? fallback;
  const set = useCallback((next: string) => patch({ [name]: next === fallback ? null : next }), [patch, name, fallback]);
  return [value, set];
}

/** Число или «все» (`null`) — выбранная группа, курс, отделение. */
export function useUrlNumber(name: string): [number | null, (next: number | null) => void] {
  const [raw, setRaw] = useUrlParam(name);
  const parsed = raw === "" ? null : Number(raw);
  const value = parsed !== null && Number.isFinite(parsed) ? parsed : null;
  const set = useCallback((next: number | null) => setRaw(next === null ? "" : String(next)), [setRaw]);
  return [value, set];
}

/** Флажок («показать архив», «только без куратора»): в адресе — `1`, выключенный не пишется. */
export function useUrlFlag(name: string): [boolean, (next: Update<boolean>) => void] {
  const [raw, setRaw] = useUrlParam(name);
  const value = raw === "1";
  const set = useCallback(
    (next: Update<boolean>) => setRaw((typeof next === "function" ? next(value) : next) ? "1" : ""),
    [setRaw, value]
  );
  return [value, set];
}

/** Сортировка таблицы: `?sort=code.desc`. Неизвестный столбец — как отдал сервер. */
export function useUrlSort<K extends string>(
  valid: readonly K[],
  name = "sort"
): [SortState<K> | null, (next: Update<SortState<K> | null>) => void] {
  const [raw, setRaw] = useUrlParam(name);
  const [key, dir] = raw.split(".");
  const value: SortState<K> | null =
    (valid as readonly string[]).includes(key) && (dir === "asc" || dir === "desc") ? { key: key as K, dir: dir as SortDir } : null;
  const set = useCallback(
    (next: Update<SortState<K> | null>) => {
      const resolved = typeof next === "function" ? next(value) : next;
      setRaw(resolved ? `${resolved.key}.${resolved.dir}` : "");
    },
    // value пересоздаётся на каждом рендере, поэтому зависим от строки адреса.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [setRaw, raw]
  );
  return [value, set];
}
