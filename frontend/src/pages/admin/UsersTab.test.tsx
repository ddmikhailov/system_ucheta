import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../../api/client";
import type { UserAdmin } from "../../api/types";
import { renderPage } from "../../test/utils";
import UsersTab from "./UsersTab";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);
const patch = vi.mocked(api.patch);
const del = vi.mocked(api.delete);

const DEPARTMENTS = [
  { id: 1, name: "Диджитал", is_active: true },
  { id: 2, name: "Моссовет", is_active: true },
];

function user(id: number, name: string, over: Partial<UserAdmin> = {}): UserAdmin {
  return {
    id, username: `user${id}`, full_name: name, role: "curator", display_title: null, department_id: 1,
    is_active: true, has_password: true, must_change_password: false, is_locked: false, ...over,
  };
}

let users: UserAdmin[];

beforeEach(() => {
  for (const fn of [post, patch, del]) fn.mockReset();
  users = [
    user(1, "Админов Админ", { role: "admin", department_id: null }),
    user(2, "Иванова Анна"),
    user(3, "Петров Пётр", { role: "dept_head" }),
    user(4, "Сидорова Софья", { role: "curator", department_id: 2 }),
    user(5, "Архивов Артём", { is_active: false }),
  ];
  get.mockReset();
  get.mockImplementation(async (path: string) => {
    if (path === "/admin/users") return users;
    if (path === "/admin/departments") return DEPARTMENTS;
    return [];
  });
});

const row = (name: string) => screen.getByText(name).closest("tr") as HTMLElement;

describe("UsersTab — список", () => {
  it("показывает ФИО, логин, роль, отделение и статус; архивные скрыты под кнопкой", async () => {
    const user = userEvent.setup();
    renderPage(<UsersTab canEdit canCreate />, { role: "admin", user: { id: 1 } });
    await screen.findByText("Иванова Анна");
    const r = row("Иванова Анна");
    expect(within(r).getByText("user2")).toBeInTheDocument();
    expect(within(r).getByText("Куратор")).toBeInTheDocument();
    expect(within(r).getByText("Диджитал")).toBeInTheDocument();
    expect(within(r).getByText("активен")).toBeInTheDocument();
    expect(within(row("Админов Админ")).getByText("—")).toBeInTheDocument(); // у админа отделения нет
    expect(screen.queryByText("Архивов Артём")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Архив (1)" }));
    expect(within(row("Архивов Артём")).getByText("в архиве")).toBeInTheDocument();
  });

  it("показывает «нужен пароль», «ждёт смены» и «заблокирован»", async () => {
    users = [
      user(2, "Без Пароля", { has_password: false }),
      user(3, "Ждёт Смены", { must_change_password: true }),
      user(4, "Заблокирован Зуев", { is_locked: true }),
    ];
    renderPage(<UsersTab canEdit canCreate />, { role: "admin" });
    await screen.findByText("Без Пароля");
    expect(within(row("Без Пароля")).getByText("нет пароля")).toBeInTheDocument();
    expect(within(row("Ждёт Смены")).getByText("ждёт смены пароля")).toBeInTheDocument();
    expect(within(row("Заблокирован Зуев")).getByText("заблокирован")).toBeInTheDocument();
  });

  it("поиск по ФИО, фильтры по роли и по отделению", async () => {
    const u = userEvent.setup();
    renderPage(<UsersTab canEdit canCreate />, { role: "admin" });
    await screen.findByText("Иванова Анна");
    await u.type(screen.getByPlaceholderText("Поиск по ФИО"), "петров");
    expect(screen.getByText("Петров Пётр")).toBeInTheDocument();
    expect(screen.queryByText("Иванова Анна")).not.toBeInTheDocument();
    await u.clear(screen.getByPlaceholderText("Поиск по ФИО"));

    const [roleFilter, departmentFilter] = screen.getAllByRole("combobox").slice(-2);
    await u.selectOptions(roleFilter, "dept_head");
    expect(screen.getByText("Петров Пётр")).toBeInTheDocument();
    expect(screen.queryByText("Иванова Анна")).not.toBeInTheDocument();
    await u.selectOptions(roleFilter, "all");
    await u.selectOptions(departmentFilter, "2");
    expect(screen.getByText("Сидорова Софья")).toBeInTheDocument();
    expect(screen.queryByText("Иванова Анна")).not.toBeInTheDocument();
  });

  it("страницы по 15: переключение и возврат на допустимую страницу, когда фильтр сократил список", async () => {
    const u = userEvent.setup();
    users = Array.from({ length: 20 }, (_, i) => user(100 + i, `Пользователь ${String(i).padStart(2, "0")}`));
    renderPage(<UsersTab canEdit canCreate />, { role: "admin" });
    await screen.findByText("Пользователь 00");
    expect(screen.getByText("Страница 1 из 2")).toBeInTheDocument();
    expect(screen.queryByText("Пользователь 15")).not.toBeInTheDocument();
    await u.click(screen.getByRole("button", { name: "Вперёд →" }));
    expect(screen.getByText("Пользователь 15")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Вперёд →" })).toBeDisabled();

    // Стоя на второй странице, сужаем список до одного человека: таблица не должна оказаться пустой.
    await u.type(screen.getByPlaceholderText("Поиск по ФИО"), "Пользователь 03");
    expect(screen.getByText("Пользователь 03")).toBeInTheDocument();
    expect(screen.queryByText("Пользователей нет.")).not.toBeInTheDocument();
    expect(screen.queryByText(/Страница/)).not.toBeInTheDocument();
  });

  it("без права правки ФИО — не кнопка и формы добавления нет", async () => {
    renderPage(<UsersTab canEdit={false} canCreate={false} />, { role: "edu_department" });
    await screen.findByText("Иванова Анна");
    expect(screen.queryByRole("button", { name: "Иванова Анна" })).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Логин")).not.toBeInTheDocument();
  });

  it("ошибка загрузки показывается", async () => {
    get.mockImplementation(async (path: string) => {
      if (path === "/admin/users") throw new ApiError(403, "Недостаточно прав");
      return DEPARTMENTS;
    });
    renderPage(<UsersTab canEdit canCreate />, { role: "admin" });
    expect(await screen.findByText("Недостаточно прав")).toBeInTheDocument();
  });
});

describe("UsersTab — создание", () => {
  async function fill(u: ReturnType<typeof userEvent.setup>, name = "Новая Нина", login = "nina") {
    await u.type(screen.getByPlaceholderText("ФИО"), name);
    await u.type(screen.getByPlaceholderText("Логин"), login);
  }

  it("создаёт пользователя и сразу показывает выданный пароль", async () => {
    const u = userEvent.setup();
    post.mockResolvedValueOnce(user(9, "Новая Нина", { username: "nina" }));
    post.mockResolvedValueOnce({ username: "nina", password: "Tmp-Pass-123" });
    renderPage(<UsersTab canEdit canCreate />, { role: "admin" });
    await screen.findByText("Иванова Анна");
    await fill(u);
    await u.click(screen.getByRole("button", { name: "Добавить пользователя" }));
    expect(post).toHaveBeenNthCalledWith(1, "/admin/users", {
      full_name: "Новая Нина", username: "nina", role: "curator", department_id: 1,
    });
    expect(post).toHaveBeenNthCalledWith(2, "/admin/users/9/set-password", {});
    expect(await screen.findByText("Tmp-Pass-123")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("ФИО")).toHaveValue("");
  });

  it("роль без отделения (администратор) уходит с department_id=null и без выбора отделения", async () => {
    const u = userEvent.setup();
    post.mockResolvedValueOnce(user(9, "Новый Админ"));
    post.mockResolvedValueOnce({ username: "x", password: "p" });
    renderPage(<UsersTab canEdit canCreate />, { role: "admin" });
    await screen.findByText("Иванова Анна");
    await fill(u, "Новый Админ", "newadmin");
    await u.selectOptions(screen.getAllByRole("combobox")[0], "admin");
    await u.click(screen.getByRole("button", { name: "Добавить пользователя" }));
    expect(post.mock.calls[0][1]).toMatchObject({ role: "admin", department_id: null });
  });

  it("список ролей зависит от того, кто создаёт: тьютор не может завести зав. отделением и админа", async () => {
    renderPage(<UsersTab canEdit canCreate />, { role: "tutor" });
    await screen.findByText("Иванова Анна");
    const roleSelect = screen.getAllByRole("combobox")[0];
    const options = within(roleSelect).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Куратор", "Заместитель куратора", "Социальный педагог", "Педагог-психолог"]);
  });

  it("зав. отделением и тьютор видят в выборе только своё отделение", async () => {
    renderPage(<UsersTab canEdit canCreate />, { role: "dept_head", user: { department_name: "Моссовет" } });
    await screen.findByText("Иванова Анна");
    const departmentSelect = screen.getAllByRole("combobox")[1];
    expect(within(departmentSelect).getAllByRole("option").map((o) => o.textContent)).toEqual(["Моссовет"]);
  });

  it("занятый логин — сообщение сервера, второй запрос не уходит, введённое остаётся", async () => {
    const u = userEvent.setup();
    post.mockRejectedValue(new ApiError(400, "Логин уже занят"));
    renderPage(<UsersTab canEdit canCreate />, { role: "admin" });
    await screen.findByText("Иванова Анна");
    await fill(u, "Новая Нина", "user2");
    await u.click(screen.getByRole("button", { name: "Добавить пользователя" }));
    expect(await screen.findByText("Логин уже занят")).toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(1);
    expect(screen.getByPlaceholderText("Логин")).toHaveValue("user2");
  });

  it("пользователь создан, а пароль выдать не удалось: ошибка объясняет, что делать, список обновляется", async () => {
    const u = userEvent.setup();
    post.mockResolvedValueOnce(user(9, "Новая Нина", { username: "nina", has_password: false }));
    post.mockRejectedValueOnce(new ApiError(500, "Сервер недоступен"));
    renderPage(<UsersTab canEdit canCreate />, { role: "admin" });
    await screen.findByText("Иванова Анна");
    const loadsBefore = get.mock.calls.filter((c) => c[0] === "/admin/users").length;
    await fill(u);
    await u.click(screen.getByRole("button", { name: "Добавить пользователя" }));
    expect(await screen.findByText(/«Новая Нина» создан, но пароль выдать не удалось.*Сервер недоступен.*в профиле/)).toBeInTheDocument();
    await waitFor(() => expect(get.mock.calls.filter((c) => c[0] === "/admin/users").length).toBe(loadsBefore + 1));
    expect(screen.getByPlaceholderText("ФИО")).toHaveValue(""); // форму не нужно отправлять повторно
  });
});

describe("UsersTab — профиль пользователя", () => {
  async function openProfile(name: string, role = "admin", me = {}) {
    const u = userEvent.setup();
    renderPage(<UsersTab canEdit canCreate />, { role, user: { id: 1, ...me } });
    await u.click(await screen.findByRole("button", { name }));
    return { u, dialog: await screen.findByRole("dialog", { name }) };
  }

  it("сохраняет ФИО, логин, роль и отделение", async () => {
    const { u, dialog } = await openProfile("Иванова Анна");
    patch.mockResolvedValue({});
    const name = within(dialog).getByDisplayValue("Иванова Анна");
    await u.clear(name);
    await u.type(name, "Иванова Анна Петровна");
    await u.selectOptions(within(dialog).getAllByRole("combobox")[0], "deputy_curator");
    await u.click(within(dialog).getByRole("button", { name: "Сохранить" }));
    expect(patch).toHaveBeenCalledWith("/admin/users/2", {
      username: "user2", full_name: "Иванова Анна Петровна", role: "deputy_curator", department_id: 1,
    });
    expect(await within(dialog).findByText("Сохранено")).toBeInTheDocument();
  });

  it("свою роль и отделение менять нельзя: поле роли заблокировано, в запросе их нет", async () => {
    const { u, dialog } = await openProfile("Админов Админ");
    patch.mockResolvedValue({});
    expect(within(dialog).getByDisplayValue("Администратор")).toBeDisabled();
    await u.click(within(dialog).getByRole("button", { name: "Сохранить" }));
    expect(patch).toHaveBeenCalledWith("/admin/users/1", { username: "user1", full_name: "Админов Админ" });
    expect(within(dialog).queryByRole("button", { name: "В архив" })).not.toBeInTheDocument(); // себя в архив нельзя
  });

  it("сброс пароля показывает новый пароль; для пользователя без пароля кнопка называется «Выдать пароль»", async () => {
    users = [user(2, "Иванова Анна", { has_password: false })];
    const { u, dialog } = await openProfile("Иванова Анна");
    post.mockResolvedValue({ username: "user2", password: "Gen-Pass-777" });
    await u.click(within(dialog).getByRole("button", { name: "Выдать пароль" }));
    expect(post).toHaveBeenCalledWith("/admin/users/2/set-password", {});
    expect(await within(dialog).findByText("Gen-Pass-777")).toBeInTheDocument();
  });

  it("свой пароль: короче 10 символов не отправляется, подходящий уходит в запрос", async () => {
    const { u, dialog } = await openProfile("Иванова Анна");
    await u.click(within(dialog).getByRole("button", { name: "Задать свой пароль" }));
    const input = within(dialog).getByPlaceholderText("Свой пароль");
    expect(input).toHaveAttribute("minlength", "10"); // как на сервере
    await u.type(input, "ninechars");
    await u.click(within(dialog).getByRole("button", { name: "Задать" }));
    expect(post).not.toHaveBeenCalled(); // 9 символов — не пускает проверка длины

    post.mockResolvedValue({ username: "user2", password: "LongEnough1!" });
    await u.clear(input);
    await u.type(input, "LongEnough1!");
    await u.click(within(dialog).getByRole("button", { name: "Задать" }));
    expect(post).toHaveBeenCalledWith("/admin/users/2/set-password", { password: "LongEnough1!" });
    expect(await within(dialog).findByText("LongEnough1!")).toBeInTheDocument();
    expect(within(dialog).queryByPlaceholderText("Свой пароль")).not.toBeInTheDocument();
  });

  it("слабый пароль — сообщение сервера", async () => {
    const { u, dialog } = await openProfile("Иванова Анна");
    await u.click(within(dialog).getByRole("button", { name: "Задать свой пароль" }));
    post.mockRejectedValue(new ApiError(400, "Пароль слишком простой"));
    await u.type(within(dialog).getByPlaceholderText("Свой пароль"), "password123");
    await u.click(within(dialog).getByRole("button", { name: "Задать" }));
    expect(await within(dialog).findByText("Пароль слишком простой")).toBeInTheDocument();
  });

  it("«Разблокировать» есть только у заблокированного", async () => {
    users = [user(2, "Иванова Анна", { is_locked: true }), user(3, "Петров Пётр")];
    const first = await openProfile("Иванова Анна");
    post.mockResolvedValue({});
    await first.u.click(within(first.dialog).getByRole("button", { name: "Разблокировать" }));
    expect(post).toHaveBeenCalledWith("/admin/users/2/unlock");

    await first.u.click(within(first.dialog).getByRole("button", { name: "Закрыть" }));
    await first.u.click(screen.getByRole("button", { name: "Петров Пётр" }));
    const second = await screen.findByRole("dialog", { name: "Петров Пётр" });
    expect(within(second).queryByRole("button", { name: "Разблокировать" })).not.toBeInTheDocument();
  });

  it("архивация закрывает окно, а «Удалить насовсем» есть только у архивного", async () => {
    const { u, dialog } = await openProfile("Иванова Анна");
    patch.mockResolvedValue({});
    expect(within(dialog).queryByRole("button", { name: "Удалить насовсем" })).not.toBeInTheDocument();
    await u.click(within(dialog).getByRole("button", { name: "В архив" }));
    expect(patch).toHaveBeenCalledWith("/admin/users/2", { is_active: false });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("удаление спрашивает подтверждение, а итог показывается во вкладке после закрытия окна", async () => {
    const u = userEvent.setup();
    renderPage(<UsersTab canEdit canCreate />, { role: "admin", user: { id: 1 } });
    await screen.findByText("Иванова Анна");
    await u.click(screen.getByRole("button", { name: "Архив (1)" }));
    await u.click(screen.getByRole("button", { name: "Архивов Артём" }));
    const dialog = await screen.findByRole("dialog", { name: "Архивов Артём" });

    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    await u.click(within(dialog).getByRole("button", { name: "Удалить насовсем" }));
    expect(del).not.toHaveBeenCalled();

    confirm.mockReturnValueOnce(true);
    del.mockResolvedValue({ deleted: false, anonymized: true, detail: "Есть история действий — данные обезличены" });
    await u.click(within(dialog).getByRole("button", { name: "Удалить насовсем" }));
    expect(del).toHaveBeenCalledWith("/admin/users/5");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByText("Есть история действий — данные обезличены")).toBeInTheDocument(); // видно вкладке, не потеряно
  });

  it("зав. отделением не меняет отделение пользователя (поля нет)", async () => {
    const { dialog } = await openProfile("Иванова Анна", "dept_head", { id: 99, department_name: "Диджитал" });
    expect(within(dialog).queryByText("Отделение")).not.toBeInTheDocument();
  });

  it("Esc закрывает окно", async () => {
    const { u } = await openProfile("Иванова Анна");
    await u.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
