import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, getToken, setToken } from "../api/client";
import type { MeResponse } from "../api/types";
import { AuthContext } from "./authContextObject";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MeResponse | null>(null);
  // Без токена сразу известно, что грузить нечего — раньше эффект всё равно
  // синхронно вызывал setLoading(false) на первом рендере (oxlint
  // react/set-state-in-effect, см. TODO.md 5); теперь это уже верное
  // начальное значение, а не побочный эффект.
  const [loading, setLoading] = useState(() => !!getToken());

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.get<MeResponse>("/auth/me");
      setUser(me);
    } catch {
      setToken(null);
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
    if (getToken()) refresh();
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
    const res = await api.post<{ access_token: string }>("/auth/login", { username, password });
    setToken(res.access_token);
    await refresh();
  }, [refresh]);

  const loginWithToken = useCallback(async (token: string) => {
    setToken(token);
    await refresh();
  }, [refresh]);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, loginWithToken, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}
