import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { usePatchSearch } from "./useUrlState";

/** Активная вкладка живёт в адресе (?tab=…): ссылкой можно поделиться, а «Назад»
 * и обновление страницы возвращают на ту же вкладку. Неизвестное значение — вкладка по умолчанию. */
export function useTabParam<T extends string>(valid: readonly T[], fallback: T, name = "tab"): [T, (next: string) => void] {
  const [params] = useSearchParams();
  const patchSearch = usePatchSearch();
  const raw = params.get(name);
  const active = raw && (valid as readonly string[]).includes(raw) ? (raw as T) : fallback;
  const setActive = useCallback(
    (next: string) => patchSearch({ [name]: next === fallback ? null : next }),
    [patchSearch, fallback, name]
  );
  return [active, setActive];
}
