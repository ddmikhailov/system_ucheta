import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api/client";
import type { MeResponse } from "../api/types";
import { AuthContext } from "./authContextObject";
import { clearNavMemory } from "../utils/navMemory";

// Пока вкладка открыта, интерфейс периодически спрашивает /auth/me: сервер продлевает сессию тому, кто работает
// (скользящее продление), и человек не вылетает на вход посреди отметок. В скрытой вкладке не спрашиваем.
const SESSION_TOUCH_MS = 30 * 60_000;
// Вернулись во вкладку (телефон разблокировали, переключились из мессенджера) — продлеваем, но не чаще раза в 5 минут.
const SESSION_TOUCH_ON_RETURN_MS = 5 * 60_000;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MeResponse | null>(null);
  // Сессия живёт в HttpOnly-cookie, и со стороны страницы её наличие не видно —
  // при старте всегда спрашиваем сервер, кто мы (нет сессии — 401 и экран входа).
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const me = await api.get<MeResponse>("/auth/me");
      setUser(me);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Загрузка текущего пользователя при монтировании — setState происходит
    // только после await внутри refresh(), не синхронно в теле эффекта;
    // без этого разово выполнить запрос на старте нечем (см. TODO.md 5).
    // oxlint-disable-next-line react/set-state-in-effect
    refresh();
  }, [refresh]);

  useEffect(() => {
    // Токен истёк/отозван (401 на любой запрос, не только на /auth/me) —
    // без этого пользователь оставался "залогиненным" в интерфейсе и видел
    // только ошибки, пока не перезагружал страницу вручную (см. TODO.md 4).
    // setState здесь вызывается из обработчика внешнего события (именно
    // тот случай, который правило react/set-state-in-effect само называет
    // корректным), а не синхронно в теле эффекта — ложное срабатывание.
    // oxlint-disable-next-line react/set-state-in-effect
    const onUnauthorized = () => setUser(null);
    window.addEventListener("auth:unauthorized", onUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", onUnauthorized);
  }, []);

  // Тихое продление: обновляет пользователя, только если он поменялся (иначе страницы, зависящие от user,
  // перезагружали бы данные каждые полчаса). Сетевая ошибка не разлогинивает — попробуем в следующий раз;
  // истёкшую сессию (401) обрабатывает событие auth:unauthorized выше.
  const lastTouch = useRef(0);
  const touchSession = useCallback(async () => {
    lastTouch.current = Date.now();
    try {
      const me = await api.get<MeResponse>("/auth/me");
      setUser((prev) => (prev && JSON.stringify(prev) === JSON.stringify(me) ? prev : me));
    } catch {
      // см. выше
    }
  }, []);

  const signedIn = user !== null;
  useEffect(() => {
    if (!signedIn) return;
    lastTouch.current = Date.now();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") touchSession();
    }, SESSION_TOUCH_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible" && Date.now() - lastTouch.current > SESSION_TOUCH_ON_RETURN_MS) touchSession();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [signedIn, touchSession]);

  const login = useCallback(async (username: string, password: string) => {
    // Сервер сам ставит cookie сессии; токен в ответе странице не нужен.
    await api.post("/auth/login", { username, password });
    // Новый вход начинается с главного экрана: путь прошлого пользователя этой вкладки забываем.
    clearNavMemory();
    await refresh();
  }, [refresh]);

  const logout = useCallback(() => {
    // Выход только из этого браузера: сервер стирает cookie; даже если запрос не дошёл, интерфейс выходит сразу.
    api.post("/auth/logout").catch(() => undefined);
    clearNavMemory();
    setUser(null);
  }, []);

  const logoutAll = useCallback(async () => {
    // Здесь интерфейс выходит, только когда сервер подтвердил: иначе человек думал бы, что другие сессии закрыты.
    await api.post("/auth/logout-all");
    clearNavMemory();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, logoutAll, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}
