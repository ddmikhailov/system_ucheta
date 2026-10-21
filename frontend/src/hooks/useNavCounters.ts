import { useCallback, useEffect, useState } from "react";
import { api, API_CHANGED_EVENT } from "../api/client";

export type CounterKey = "my_day" | "my_tasks" | "review" | "journal_changes";
/** Числа на пунктах меню и непрочитанные уведомления колокольчика — один ответ `/my-day/counters`. */
export type NavCounters = Partial<Record<CounterKey | "notifications", number>>;

/** При переходах между разделами — не чаще раза в 30 с (если с тех пор ничего не меняли). */
export const COUNTERS_MIN_INTERVAL_MS = 30_000;
/** Фоновое обновление, пока вкладка видна. */
export const COUNTERS_POLL_MS = 60_000;
/** Периодические задачи и напоминания о сроках (POST /notifications/check). */
export const CHECK_INTERVAL_MS = 5 * 60_000;

// Состояние общее для всех экземпляров Layout: страницы оборачиваются в Layout каждая своя, и при переходе
// компонент может создаваться заново — ограничение «раз в 30 с» не должно от этого сбрасываться.
const shared = {
  userId: null as number | null,
  counters: {} as NavCounters,
  fetchedAt: 0,
  checkedAt: 0,
  // Любое сохранение (POST/PUT/PATCH/DELETE) могло изменить числа: следующий переход спросит сервер сразу.
  stale: true,
};
const listeners = new Set<(c: NavCounters) => void>();

function publish(next: NavCounters) {
  shared.counters = next;
  listeners.forEach((l) => l(next));
}

if (typeof window !== "undefined") {
  window.addEventListener(API_CHANGED_EVENT, () => {
    shared.stale = true;
  });
}

/** Сброс общего состояния (смена пользователя, тесты). */
export function resetNavCounters(userId: number | null = null) {
  shared.userId = userId;
  shared.counters = {};
  shared.fetchedAt = 0;
  shared.checkedAt = 0;
  shared.stale = true;
}

/** Счётчики меню и колокольчика. Сервер спрашивается при переходе (не чаще раза в 30 с), раз в минуту по таймеру
 * и при возврате на вкладку; скрытая вкладка ничего не запрашивает. Раз в 5 минут — проверка сроков задач. */
export function useNavCounters(userId: number | null | undefined, pathname: string) {
  if ((userId ?? null) !== shared.userId) resetNavCounters(userId ?? null);
  const [counters, setCounters] = useState<NavCounters>(shared.counters);

  useEffect(() => {
    listeners.add(setCounters);
    return () => {
      listeners.delete(setCounters);
    };
  }, []);

  const refresh = useCallback(
    (force: boolean) => {
      if (userId == null || document.hidden) return;
      const now = Date.now();
      if (!force && !shared.stale && now - shared.fetchedAt < COUNTERS_MIN_INTERVAL_MS) return;
      shared.fetchedAt = now;
      shared.stale = false;
      api
        .get<NavCounters>("/my-day/counters")
        .then((c) => {
          if (shared.userId === userId) publish(c && typeof c === "object" && !Array.isArray(c) ? c : {});
        })
        .catch(() => {
          if (shared.userId === userId) publish({});
        });
    },
    [userId],
  );

  const check = useCallback(() => {
    if (userId == null || document.hidden) return;
    const now = Date.now();
    if (now - shared.checkedAt < CHECK_INTERVAL_MS) return;
    shared.checkedAt = now;
    api
      .post<{ unread: number }>("/notifications/check")
      .then((r) => {
        if (shared.userId === userId && typeof r?.unread === "number") publish({ ...shared.counters, notifications: r.unread });
      })
      .catch(() => {});
  }, [userId]);

  // Переход между разделами: сдали день, отправили задачу — число уменьшилось.
  useEffect(() => {
    refresh(false);
  }, [pathname, refresh]);

  useEffect(() => {
    check();
    const id = setInterval(() => {
      refresh(true);
      check();
    }, COUNTERS_POLL_MS);
    function onVisible() {
      if (document.hidden) return;
      refresh(false);
      check();
    }
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refresh, check]);

  /** Колокольчик сам знает, что пометил прочитанным, — число меняем сразу, не дожидаясь опроса. */
  const setUnread = useCallback((unread: number) => publish({ ...shared.counters, notifications: unread }), []);

  return { counters, setUnread };
}
