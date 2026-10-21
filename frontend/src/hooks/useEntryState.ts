import { useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { useLocation } from "react-router-dom";
import { entryState, setEntryStateValue } from "../utils/navMemory";

/** Как useState, но значение помнится за записью истории в пределах вкладки: ушли в карточку
 * студента и вернулись «Назад» (или обновили страницу) — фильтр, поиск, сортировка на месте.
 * Новый переход в раздел через меню — новая запись и значение по умолчанию. Значение должно
 * переживать JSON (строки, числа, флажки, простые объекты). */
export function useEntryState<T>(name: string, initial: T | (() => T)): [T, Dispatch<SetStateAction<T>>] {
  const location = useLocation();
  const [value, setValue] = useState<T>(() => {
    const saved = entryState(location.key);
    if (name in saved) return saved[name] as T;
    return typeof initial === "function" ? (initial as () => T)() : initial;
  });
  const first = useRef(true);
  useEffect(() => {
    // Значение по умолчанию не записываем: в памяти только то, что человек поменял.
    if (first.current) {
      first.current = false;
      return;
    }
    setEntryStateValue(location.key, name, value);
  }, [name, value, location.key]);
  return [value, setValue];
}
