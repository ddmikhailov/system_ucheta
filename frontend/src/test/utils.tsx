import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
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
  /** Подмена функций контекста авторизации (например, logout — чтобы проверить вызов). */
  auth?: Partial<AuthContextValue>;
}

/** Рисует компонент внутри роутера и контекста авторизации с заданной ролью. */
export function renderPage(ui: ReactElement, { route = "/", path = "*", role = "admin", user, auth }: Options = {}) {
  const value: AuthContextValue = {
    user: role === null ? null : makeUser(role, user),
    loading: false,
    login: async () => undefined,
    logout: () => undefined,
    logoutAll: async () => undefined,
    refresh: async () => undefined,
    ...auth,
  };
  // Роутер с данными, как в приложении (createBrowserRouter): иначе useBlocker в журнале недоступен.
  const router = createMemoryRouter([{ path, element: ui }], { initialEntries: [route] });
  return render(
    <AuthContext.Provider value={value}>
      <RouterProvider router={router} />
    </AuthContext.Provider>
  );
}
