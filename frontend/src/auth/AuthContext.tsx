import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api/client";
import type { MeResponse } from "../api/types";
import { AuthContext } from "./authContextObject";

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

  const login = useCallback(async (username: string, password: string) => {
    // Сервер сам ставит cookie сессии; токен в ответе странице не нужен.
    await api.post("/auth/login", { username, password });
    await refresh();
  }, [refresh]);

  const logout = useCallback(() => {
    // Выход отзывает сессию на сервере; даже если запрос не дошёл, интерфейс выходит сразу.
    api.post("/auth/logout").catch(() => undefined);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}
