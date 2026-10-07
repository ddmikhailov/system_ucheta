import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthContext } from "../auth/authContextObject";
import type { AuthContextValue } from "../auth/authContextObject";
import type { MeResponse } from "../api/types";

export function makeUser(role: string, overrides: Partial<MeResponse> = {}): MeResponse {
  return {
    id: 1,
    full_name: "Тестов Тест",
    role,
    display_title: null,
    department_name: "Диджитал",
    groups: [],
    dept_head_name: null,
    must_change_password: false,
    ...overrides,
  };
}

interface Options {
  /** Начальный адрес (по умолчанию "/"). */
  route?: string;
  /** Шаблон маршрута, под которым монтируется страница, — нужен страницам с параметрами в пути. */
  path?: string;
  /** Роль вошедшего пользователя; null — не вошёл. */
  role?: string | null;
  user?: Partial<MeResponse>;
}

/** Рисует компонент внутри роутера и контекста авторизации с заданной ролью. */
export function renderPage(ui: ReactElement, { route = "/", path = "*", role = "admin", user }: Options = {}) {
  const value: AuthContextValue = {
    user: role === null ? null : makeUser(role, user),
    loading: false,
    login: async () => undefined,
    logout: () => undefined,
    refresh: async () => undefined,
  };
  return render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path={path} element={ui} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}
