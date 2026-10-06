import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

/** Группа и прочие параметры страницы в адресе. На странице группы (`fixedGroupId`) группа задана
 * маршрутом: в адрес она не пишется, а остальные параметры (вкладка, год, семестр) сохраняются. */
export function useGroupParams(fixedGroupId?: number) {
  const [params, setParams] = useSearchParams();
  const groupId = fixedGroupId != null ? String(fixedGroupId) : params.get("group");
  const update = useCallback(
    (patch: Record<string, string | null>, options?: { replace?: boolean }) =>
      setParams((prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, value] of Object.entries(patch)) {
          if (value === null) next.delete(key);
          else next.set(key, value);
        }
        if (fixedGroupId != null) next.delete("group");
        return next;
      }, options),
    [setParams, fixedGroupId]
  );
  return { params, groupId, update };
}
