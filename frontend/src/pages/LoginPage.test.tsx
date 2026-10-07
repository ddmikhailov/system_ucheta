import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { AuthContext } from "../auth/authContextObject";
import type { AuthContextValue } from "../auth/authContextObject";
import { makeUser } from "../test/utils";
import LoginPage from "./LoginPage";

function renderLogin(over: Partial<AuthContextValue> = {}) {
  const value: AuthContextValue = {
    user: null, loading: false, login: vi.fn().mockResolvedValue(undefined),
    logout: vi.fn(), refresh: vi.fn(), ...over,
  };
  render(
    <AuthContext.Provider value={value}>
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div>главная</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
  return value;
}

describe("LoginPage", () => {
  it("входит по логину и паролю и переходит на главную", async () => {
    const user = userEvent.setup();
    const value = renderLogin();
    await user.type(screen.getByLabelText("Логин"), "kurator");
    await user.type(document.querySelector('input[type="password"]') as HTMLInputElement, "Secret123!");
    await user.click(screen.getByRole("button", { name: "Войти" }));
    expect(value.login).toHaveBeenCalledWith("kurator", "Secret123!");
    expect(await screen.findByText("главная")).toBeInTheDocument();
  });

  it("неверный пароль: показывает сообщение сервера и остаётся на странице", async () => {
    const user = userEvent.setup();
    renderLogin({ login: vi.fn().mockRejectedValue(new ApiError(401, "Неверный логин или пароль")) });
    await user.type(screen.getByLabelText("Логин"), "x");
    await user.type(document.querySelector('input[type="password"]') as HTMLInputElement, "y");
    await user.click(screen.getByRole("button", { name: "Войти" }));
    expect(await screen.findByText("Неверный логин или пароль")).toBeInTheDocument();
    expect(screen.queryByText("главная")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Войти" })).toBeEnabled();
  });

  it("непонятная ошибка (сеть) — общее сообщение", async () => {
    const user = userEvent.setup();
    renderLogin({ login: vi.fn().mockRejectedValue(new TypeError("Failed to fetch")) });
    await user.type(screen.getByLabelText("Логин"), "x");
    await user.type(document.querySelector('input[type="password"]') as HTMLInputElement, "y");
    await user.click(screen.getByRole("button", { name: "Войти" }));
    expect(await screen.findByText("Не удалось войти")).toBeInTheDocument();
  });

  it("слишком частые попытки: показывает ответ сервера про блокировку", async () => {
    const user = userEvent.setup();
    renderLogin({ login: vi.fn().mockRejectedValue(new ApiError(429, "Слишком много попыток входа — попробуйте позже")) });
    await user.type(screen.getByLabelText("Логин"), "x");
    await user.type(document.querySelector('input[type="password"]') as HTMLInputElement, "y");
    await user.click(screen.getByRole("button", { name: "Войти" }));
    expect(await screen.findByText(/Слишком много попыток входа/)).toBeInTheDocument();
  });

  it("«Показать» переключает видимость пароля", async () => {
    const user = userEvent.setup();
    renderLogin();
    const password = document.querySelector('input[autocomplete="current-password"], input[type="password"]') as HTMLInputElement;
    expect(password.type).toBe("password");
    await user.click(screen.getByRole("button", { name: "Показать" }));
    expect(password.type).toBe("text");
  });

  it("поле пароля называется «Пароль» (без текста кнопки «Показать»), а кнопка доступна с клавиатуры", async () => {
    const user = userEvent.setup();
    renderLogin();
    const password = screen.getByLabelText("Пароль") as HTMLInputElement;
    expect(password.tagName).toBe("INPUT");
    const toggle = screen.getByRole("button", { name: "Показать" });
    expect(toggle).not.toHaveAttribute("tabindex", "-1");
    expect(toggle).toHaveAttribute("aria-controls", password.id);
    password.focus();
    await user.tab();
    expect(toggle).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(password.type).toBe("text");
    expect(screen.getByRole("button", { name: "Скрыть" })).toBeInTheDocument();
  });

  it("уже вошедшего пользователя форма входа не задерживает", async () => {
    renderLogin({ user: makeUser("curator") });
    await waitFor(() => expect(screen.getByText("главная")).toBeInTheDocument());
  });

  it("пока идёт проверка сохранённого входа, форма остаётся (не мигает редиректом)", () => {
    renderLogin({ user: null, loading: true });
    expect(screen.getByRole("button", { name: "Войти" })).toBeInTheDocument();
  });
});
