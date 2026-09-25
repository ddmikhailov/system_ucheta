import { useEffect } from "react";

/** Закрытие модалки по Esc — раньше работало только по клику на фон/кнопку
 * "Отмена" (см. TODO.md 4). */
export function useEscapeKey(onClose: () => void): void {
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);
}
