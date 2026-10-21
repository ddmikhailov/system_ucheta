import { useCallback, useSyncExternalStore } from "react";
import type { To } from "react-router-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { previousUrl, subscribeNavMemory } from "../utils/navMemory";

/** Возврат «Назад» из интерфейса: если на эту страницу пришли изнутри платформы — шаг назад по
 * истории (та же группа, фильтры, прокрутка); если открыли напрямую — переход на `fallback`.
 * `from` — адрес, куда вернёт шаг назад (null, если вернёт на `fallback`). */
export function useGoBack(fallback: To): { from: string | null; goBack: () => void } {
  const location = useLocation();
  const navigate = useNavigate();
  const from = useSyncExternalStore(subscribeNavMemory, () => previousUrl(location.key));
  const goBack = useCallback(() => {
    if (from) navigate(-1);
    else navigate(fallback);
  }, [from, navigate, fallback]);
  return { from, goBack };
}
