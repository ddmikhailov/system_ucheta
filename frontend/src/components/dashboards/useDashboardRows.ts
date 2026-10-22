import { useEffect, useMemo, useRef } from "react";
import { useApi } from "../../hooks/useApi";

/** Строки вкладки витрины: загрузка с отменой устаревшего запроса (сменили день или отделение —
 * ответ по прежнему не подменит таблицу) и перезапрос, когда страница увеличила reloadKey
 * (кнопка «Обновить», возврат на вкладку браузера). */
export function useDashboardRows<T>(path: string, reloadKey: number) {
  const { data, error, loading, reload } = useApi<T[]>(path, "Ошибка загрузки");
  const seen = useRef(reloadKey);
  useEffect(() => {
    if (seen.current === reloadKey) return;
    seen.current = reloadKey;
    reload();
  }, [reloadKey, reload]);
  const rows = useMemo(() => data ?? [], [data]);
  return { rows, error, loading };
}
