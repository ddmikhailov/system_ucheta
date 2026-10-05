import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import UserMenu from "./UserMenu";

function renderMenu(onLogout = vi.fn()) {
  render(
    <MemoryRouter>
      <UserMenu name="Иванова Анна Ивановна" onLogout={onLogout} />
      <button>снаружи</button>
    </MemoryRouter>
  );
  return onLogout;
}

const toggle = () => screen.getByRole("button", { name: /Иванова Анна Ивановна/ });

describe("UserMenu", () => {
  it("закрыто по умолчанию, открывается и закрывается кликом по имени", async () => {
    const user = userEvent.setup();
    renderMenu();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    await user.click(toggle());
    expect(screen.getByRole("menu")).toBeInTheDocument();
    await user.click(toggle());
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("«Выйти» закрывает меню и вызывает выход", async () => {
    const user = userEvent.setup();
    const onLogout = renderMenu();
    await user.click(toggle());
    await user.click(screen.getByRole("menuitem", { name: "Выйти" }));
    expect(onLogout).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("«Сменить пароль» — ссылка, после перехода меню закрывается", async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(toggle());
    const link = screen.getByRole("menuitem", { name: "Сменить пароль" });
    expect(link).toHaveAttribute("href", "/change-password");
    await user.click(link);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("закрывается по Esc и по клику вне меню, но не по клику внутри панели", async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(toggle());
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();

    await user.click(toggle());
    await user.click(screen.getByRole("menu")); // по пустому месту панели
    expect(screen.getByRole("menu")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "снаружи" }));
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("тема: выбор запоминается и ставится на страницу; «Как в системе» снимает выбор", async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(toggle());
    expect(screen.getByRole("menuitemradio", { name: "Как в системе" })).toHaveAttribute("aria-checked", "true");
    await user.click(screen.getByRole("menuitemradio", { name: "Тёмная" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("kait20_theme")).toBe("dark");
    expect(screen.getByRole("menuitemradio", { name: "Тёмная" })).toHaveAttribute("aria-checked", "true");
    await user.click(screen.getByRole("menuitemradio", { name: "Как в системе" }));
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(localStorage.getItem("kait20_theme")).toBeNull();
  });
});
