import { useCallback, useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { api, ApiError, isAbortError } from "../api/client";

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  /** Перезапросить тот же адрес (после сохранения); прежние данные остаются на экране до ответа. */
  reload: () => void;
  /** Подменить данные без запроса — например, ответом PUT, который уже вернул новое состояние. */
  setData: Dispatch<SetStateAction<T | null>>;
}

/** Загрузка по GET с отменой устаревшего запроса. Раньше каждая страница писала свой
 * useEffect + api.get + loading/error, и защита от «гонки» была лишь в части мест: быстро
 * переключили группу — ответ по прежней приходил позже и затирал новую. Здесь смена адреса
 * отменяет прежний запрос, и его ответ (или ошибка) уже ничего не меняет.
 *
 * `path = null` — запроса нет (не выбрана группа, модуль выключен). Со сменой адреса данные
 * прежнего сбрасываются, чтобы под новым заголовком не мелькали чужие строки. */
export function useApi<T>(path: string | null, errorText = "Не удалось загрузить данные"): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const [loadedPath, setLoadedPath] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  // Сброс при смене адреса — во время отрисовки, а не в эффекте: иначе один кадр показал бы
  // данные прежнего адреса под новым.
  if (path !== loadedPath) {
    setLoadedPath(path);
    setData(null);
    setError(null);
    setLoading(path !== null);
  }

  useEffect(() => {
    if (path === null) return;
    const controller = new AbortController();
    api
      .get<T>(path, controller.signal)
      .then((d) => {
        // Ответ мог успеть прийти до отмены, но обработаться после неё.
        if (controller.signal.aborted) return;
        setData(d);
        setError(null);
      })
      .catch((err) => {
        if (controller.signal.aborted || isAbortError(err)) return;
        setError(err instanceof ApiError ? err.message : errorText);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [path, nonce, errorText]);

  // Признак загрузки ставится здесь и при смене адреса (выше), а не в эффекте — без лишней отрисовки.
  const reload = useCallback(() => {
    setLoading(true);
    setNonce((n) => n + 1);
  }, []);
  return { data, error, loading, reload, setData };
}
