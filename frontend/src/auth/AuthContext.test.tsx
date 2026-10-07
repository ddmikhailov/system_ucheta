import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { makeUser } from "../test/utils";
import { AuthProvider } from "./AuthContext";
import { useAuth } from "./useAuth";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);

function Probe() {
  const { user, loading, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="state">{loading ? "loading" : user ? `user:${user.role}` : "anonymous"}</span>
      <button onClick={() => login("kurator", "pw").catch(() => undefined)}>login</button>
      <button onClick={logout}>logout</button>
    </div>
  );
}

const renderAuth = () => render(<AuthProvider><Probe /></AuthProvider>);

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});

describe("AuthProvider", () => {
  it("при старте спрашивает сервер: есть сессия — сначала «загрузка», потом пользователь", async () => {
    get.mockResolvedValue(makeUser("curator"));
    renderAuth();
    expect(screen.getByTestId("state")).toHaveTextContent("loading");
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("user:curator"));
    expect(get).toHaveBeenCalledWith("/auth/me");
  });

  it("нет сессии (401) — аноним", async () => {
    get.mockRejectedValue(new ApiError(401, "Нужна авторизация"));
    renderAuth();
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("anonymous"));
  });

  it("вход отправляет логин и пароль и подгружает пользователя; токен в хранилище не пишется", async () => {
    const user = userEvent.setup();
    get.mockRejectedValueOnce(new ApiError(401, "Нужна авторизация"));
    renderAuth();
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("anonymous"));
    post.mockResolvedValue({ access_token: "new-token" });
    get.mockResolvedValue(makeUser("admin"));
    await user.click(screen.getByRole("button", { name: "login" }));
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("user:admin"));
    expect(post).toHaveBeenCalledWith("/auth/login", { username: "kurator", password: "pw" });
    expect(JSON.stringify({ ...localStorage })).not.toContain("new-token");
  });

  it("неудачный вход оставляет анонимом", async () => {
    const user = userEvent.setup();
    get.mockRejectedValue(new ApiError(401, "Нужна авторизация"));
    post.mockRejectedValue(new ApiError(401, "Неверный логин или пароль"));
    renderAuth();
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("anonymous"));
    await user.click(screen.getByRole("button", { name: "login" }));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(screen.getByTestId("state")).toHaveTextContent("anonymous");
  });

  it("выход отзывает сессию на сервере и убирает пользователя", async () => {
    const user = userEvent.setup();
    post.mockResolvedValue(undefined);
    get.mockResolvedValue(makeUser("curator"));
    renderAuth();
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("user:curator"));
    await user.click(screen.getByRole("button", { name: "logout" }));
    expect(screen.getByTestId("state")).toHaveTextContent("anonymous");
    expect(post).toHaveBeenCalledWith("/auth/logout");
  });

  it("401 на любом запросе (событие приложения) разлогинивает без перезагрузки страницы", async () => {
    get.mockResolvedValue(makeUser("curator"));
    renderAuth();
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("user:curator"));
    act(() => {
      window.dispatchEvent(new Event("auth:unauthorized"));
    });
    expect(screen.getByTestId("state")).toHaveTextContent("anonymous");
  });
});

describe("useAuth", () => {
  it("вне провайдера — понятная ошибка", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => render(<Probe />)).toThrow(/внутри AuthProvider/);
    spy.mockRestore();
  });
});
