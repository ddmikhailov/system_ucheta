import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

/** Активная вкладка живёт в адресе (?tab=…): ссылкой можно поделиться, а «Назад»
 * и обновление страницы возвращают на ту же вкладку. Неизвестное значение — вкладка по умолчанию. */
export function useTabParam<T extends string>(valid: readonly T[], fallback: T): [T, (next: string) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const active = raw && (valid as readonly string[]).includes(raw) ? (raw as T) : fallback;
  const setActive = useCallback(
    (next: string) => {
      setParams(
        (prev) => {
          const p = new URLSearchParams(prev);
          if (next === fallback) p.delete("tab");
          else p.set("tab", next);
          return p;
        },
        { replace: true }
      );
    },
    [setParams, fallback]
  );
  return [active, setActive];
}
