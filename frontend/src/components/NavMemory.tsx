import { useEffect, useLayoutEffect, useRef } from "react";
import { useLocation, useNavigationType } from "react-router-dom";
import { moveEntryState, previousUrl, savedScroll, saveScroll, setPreviousUrl } from "../utils/navMemory";

/** Сколько ждать, пока страница догрузит данные, чтобы вернуть прокрутку на прежнее место. */
const RESTORE_TIMEOUT_MS = 3000;

/** Ждёт, пока страница станет достаточно длинной, и прокручивает на `y`. Любое действие пользователя
 * (колесо, касание, клавиша) отменяет возврат — не дёргаем страницу у него из-под рук. */
function restoreScroll(y: number): () => void {
  let frame = 0;
  const started = Date.now();
  const stop = () => {
    cancelAnimationFrame(frame);
    window.removeEventListener("wheel", stop);
    window.removeEventListener("touchstart", stop);
    window.removeEventListener("keydown", stop);
  };
  window.addEventListener("wheel", stop, { passive: true });
  window.addEventListener("touchstart", stop, { passive: true });
  window.addEventListener("keydown", stop);
  const tick = () => {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    if (max >= y || Date.now() - started > RESTORE_TIMEOUT_MS) {
      window.scrollTo(0, Math.max(0, Math.min(y, max)));
      stop();
      return;
    }
    frame = requestAnimationFrame(tick);
  };
  tick();
  return stop;
}

/** Помнит путь пользователя в пределах вкладки: откуда он пришёл на каждую страницу (для кнопок
 * «← Назад», см. BackLink) и где была прокрутка. Браузерная «Назад» возвращает прокрутку, новый
 * переход на другую страницу начинается сверху, смена фильтров на месте прокрутку не трогает. */
export default function NavMemory() {
  const location = useLocation();
  const navigationType = useNavigationType();
  const current = useRef<{ key: string; url: string; pathname: string } | null>(null);

  useEffect(() => {
    if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";
    let frame = 0;
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (current.current) saveScroll(current.current.key, window.scrollY);
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
    };
  }, []);

  useLayoutEffect(() => {
    const last = current.current;
    const url = location.pathname + location.search;
    // Экран входа ни откуда не «приходит»: после выхода память пути остаётся пустой.
    if (last && last.key !== location.key && location.pathname !== "/login") {
      if (navigationType === "PUSH") setPreviousUrl(location.key, last.url);
      // Смена фильтров заменяет запись истории — «откуда пришли» переезжает на новую запись.
      else if (navigationType === "REPLACE") {
        setPreviousUrl(location.key, previousUrl(last.key));
        if (last.pathname === location.pathname) {
          moveEntryState(last.key, location.key);
          saveScroll(location.key, window.scrollY);
        }
      }
    }
    current.current = { key: location.key, url, pathname: location.pathname };

    if (navigationType === "POP") {
      const y = savedScroll(location.key);
      if (y !== null && y > 0) return restoreScroll(y);
    } else if (navigationType === "PUSH" && last && last.pathname !== location.pathname) {
      window.scrollTo(0, 0);
    }
    return undefined;
  }, [location.key, location.pathname, location.search, navigationType]);

  return null;
}
