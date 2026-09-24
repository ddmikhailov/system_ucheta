import { useEffect, useRef } from "react";
import { scrollToTop } from "../utils/scroll";

/** Прокручивает страницу наверх при появлении баннера ошибки/уведомления
 * (они рендерятся вверху страницы) — иначе результат действия не виден,
 * если админ прокрутил список вниз перед тем, как что-то применить. */
export function useScrollToTopOnChange(...signals: unknown[]): void {
  const mounted = useRef(false);

  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    const hasSignal = signals.some((s) => s !== null && s !== undefined && s !== false);
    if (hasSignal) scrollToTop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, signals);
}
