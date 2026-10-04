import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, getToken, setToken } from "../api/client";
import { AuthContext } from "../auth/authContextObject";
import { makeUser } from "../test/utils";
import ChangePasswordPage from "./ChangePasswordPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const post = vi.mocked(api.post);

function open(forced: boolean) {
  const refresh = vi.fn().mockResolvedValue(undefined);
  render(
    <AuthContext.Provider
      value={{ user: makeUser("curator", { must_change_password: forced, full_name: "Иванова Анна" }), loading: false, login: vi.fn(), loginWithToken: vi.fn(), logout: vi.fn(), refresh }}
    >
      <MemoryRouter initialEntries={["/prev", "/change-password"]} initialIndex={1}>
        <Routes>
          <Route path="/change-password" element={<ChangePasswordPage />} />
          <Route path="/" element={<div>главная</div>} />
          <Route path="/prev" element={<div>предыдущая страница</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
  return refresh;
}

const fields = () => ({
  current: screen.queryByLabelText("Текущий пароль") as HTMLInputElement | null,
  next: screen.getByLabelText("Новый пароль") as HTMLInputElement,
  repeat: screen.getByLabelText("Повторите новый пароль") as HTMLInputElement,
});

beforeEach(() => post.mockReset());

describe("ChangePasswordPage — обычная смена", () => {
  it("нужен текущий пароль; запрос уходит с обоими, новый токен сохраняется, пользователь обновляется", async () => {
    const user = userEvent.setup();
    setToken("old-token");
    post.mockResolvedValue({ ...makeUser("curator"), access_token: "new-token" });
    const refresh = open(false);
    const f = fields();
    await user.type(f.current!, "OldPassword123");
    await user.type(f.next, "NewPassword456!");
    await user.type(f.repeat, "NewPassword456!");
    await user.click(screen.getByRole("button", { name: "Сохранить пароль" }));
    expect(post).toHaveBeenCalledWith("/auth/change-password", { current_password: "OldPassword123", new_password: "NewPassword456!" });
    await waitFor(() => expect(screen.getByText("главная")).toBeInTheDocument());
    expect(getToken()).toBe("new-token"); // смена пароля отзывает прежние токены — следующий запрос должен идти уже с новым
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("пароли не совпадают — сообщение, на сервер не уходит", async () => {
    const user = userEvent.setup();
    open(false);
    const f = fields();
    await user.type(f.current!, "OldPassword123");
    await user.type(f.next, "NewPassword456!");
    await user.type(f.repeat, "Другой-пароль-789");
    await user.click(screen.getByRole("button", { name: "Сохранить пароль" }));
    expect(await screen.findByText("Пароли не совпадают")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("новый пароль короче минимума отсекается формой (10 символов, как на сервере)", async () => {
    open(false);
    const f = fields();
    expect(f.next).toHaveAttribute("minlength", "10");
    expect(f.repeat).toHaveAttribute("minlength", "10");
  });

  it("неверный текущий пароль и слабый новый — сообщения сервера, поля остаются", async () => {
    const user = userEvent.setup();
    post.mockRejectedValueOnce(new ApiError(400, "Неверный текущий пароль"));
    open(false);
    const f = fields();
    await user.type(f.current!, "WrongPassword1");
    await user.type(f.next, "NewPassword456!");
    await user.type(f.repeat, "NewPassword456!");
    await user.click(screen.getByRole("button", { name: "Сохранить пароль" }));
    expect(await screen.findByText("Неверный текущий пароль")).toBeInTheDocument();
    expect(f.next).toHaveValue("NewPassword456!");
    expect(screen.getByRole("button", { name: "Сохранить пароль" })).toBeEnabled();
  });

  it("сбой сети — общее сообщение", async () => {
    const user = userEvent.setup();
    post.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    open(false);
    const f = fields();
    await user.type(f.current!, "OldPassword123");
    await user.type(f.next, "NewPassword456!");
    await user.type(f.repeat, "NewPassword456!");
    await user.click(screen.getByRole("button", { name: "Сохранить пароль" }));
    expect(await screen.findByText("Не удалось сменить пароль")).toBeInTheDocument();
  });

  it("«Отмена» возвращает на предыдущую страницу", async () => {
    const user = userEvent.setup();
    open(false);
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(await screen.findByText("предыдущая страница")).toBeInTheDocument();
  });
});

describe("ChangePasswordPage — временный пароль", () => {
  it("текущий пароль не спрашивается и не отправляется, отмены нет, заголовок объясняет причину", async () => {
    const user = userEvent.setup();
    post.mockResolvedValue({ ...makeUser("curator"), access_token: null });
    open(true);
    expect(screen.getByRole("heading", { name: "Новый пароль" })).toBeInTheDocument();
    expect(screen.getByText(/Администратор выдал временный пароль/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Текущий пароль")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Отмена" })).not.toBeInTheDocument();
    const f = fields();
    await user.type(f.next, "NewPassword456!");
    await user.type(f.repeat, "NewPassword456!");
    await user.click(screen.getByRole("button", { name: "Сохранить пароль" }));
    expect(post).toHaveBeenCalledWith("/auth/change-password", { current_password: undefined, new_password: "NewPassword456!" });
    expect(await screen.findByText("главная")).toBeInTheDocument();
  });

  it("если сервер не вернул новый токен, прежний остаётся", async () => {
    const user = userEvent.setup();
    setToken("kept-token");
    post.mockResolvedValue({ ...makeUser("curator"), access_token: null });
    open(true);
    const f = fields();
    await user.type(f.next, "NewPassword456!");
    await user.type(f.repeat, "NewPassword456!");
    await user.click(screen.getByRole("button", { name: "Сохранить пароль" }));
    await screen.findByText("главная");
    expect(getToken()).toBe("kept-token");
  });
});
