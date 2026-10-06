import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { renderPage } from "../test/utils";
import Layout from "./Layout";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);

beforeEach(() => {
  get.mockReset();
  get.mockImplementation(async (path: string) => (path === "/notifications/unread-count" ? { unread: 0 } : []));
});

/** Названия пунктов основного меню в порядке показа. */
function menu(role: string, groups: { id: number; code: string; course: number }[] = []) {
  renderPage(<Layout><div>содержимое</div></Layout>, { role, user: { groups } });
  const nav = screen.getByRole("navigation", { name: "Разделы" });
  return within(nav).queryAllByRole("link").map((a) => a.querySelector(".nav-link__label")?.textContent);
}

describe("Layout — меню по ролям", () => {
  it.each([
    ["curator", ["Мой день", "Мои группы", "Мои задачи", "Соц. паспорт", "Индивидуальная работа"]],
    ["deputy_curator", ["Мой день", "Мои группы", "Мои задачи", "Соц. паспорт", "Индивидуальная работа"]],
    ["dept_head", ["Задачи", "Витрины", "Студенты", "Соц. паспорт", "Индивидуальная работа", "Админка"]],
    ["tutor", ["Задачи", "Витрины", "Студенты", "Соц. паспорт", "Индивидуальная работа", "Админка"]],
    ["edu_department", ["Задачи", "Витрины", "Студенты", "Соц. паспорт", "Индивидуальная работа", "Админка"]],
    ["admin", ["Задачи", "Витрины", "Студенты", "Соц. паспорт", "Индивидуальная работа", "Админка"]],
    ["social_pedagogue", ["Витрины", "Студенты", "Соц. паспорт", "Индивидуальная работа"]],
    ["psychologist", ["Витрины", "Студенты", "Соц. паспорт", "Индивидуальная работа"]],
  ])("роль %s видит свои разделы", (role, expected) => {
    expect(menu(role)).toEqual(expected);
  });

  it("специалист, который ведёт группы, получает «Мой день», «Мои группы» и «Мои задачи»", () => {
    expect(menu("psychologist", [{ id: 1, code: "СА172", course: 1 }])).toEqual([
      "Мой день", "Мои группы", "Мои задачи", "Витрины", "Студенты", "Соц. паспорт", "Индивидуальная работа",
    ]);
  });

  it("куратору не показываются управленческие разделы", () => {
    const items = menu("curator");
    for (const hidden of ["Задачи", "Витрины", "Студенты", "Админка"]) expect(items).not.toContain(hidden);
  });

  it("имя пользователя — кнопка меню, а «Сменить пароль» и «Выйти» внутри него", async () => {
    const user = userEvent.setup();
    renderPage(<Layout><div>содержимое</div></Layout>, { role: "admin", user: { full_name: "Иванова Анна" } });
    const toggle = screen.getByRole("button", { name: /Иванова Анна/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("menuitem", { name: "Выйти" })).not.toBeInTheDocument();
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("menuitem", { name: "Сменить пароль" })).toHaveAttribute("href", "/change-password");
    expect(screen.getByRole("menuitem", { name: "Выйти" })).toBeInTheDocument();
    expect(screen.getByText("содержимое")).toBeInTheDocument();
  });

  it("основное меню подписано для скринридеров и не содержит пунктов пользователя", () => {
    renderPage(<Layout><div /></Layout>, { role: "admin" });
    const nav = screen.getByRole("navigation", { name: "Разделы" });
    expect(within(nav).queryByText("Выйти")).not.toBeInTheDocument();
    expect(within(nav).queryByText("Сменить пароль")).not.toBeInTheDocument();
  });
});

describe("Layout — нижняя панель и счётчики", () => {
  function tabbar(role: string) {
    renderPage(<Layout><div /></Layout>, { role });
    return screen.getByRole("navigation", { name: "Быстрые разделы" });
  }

  it("куратор: три раздела и «Ещё» с остальными", async () => {
    const user = userEvent.setup();
    const bar = tabbar("curator");
    expect(within(bar).getAllByRole("link").map((a) => a.textContent)).toEqual(["Мой день", "Группы", "Задачи"]);
    await user.click(within(bar).getByRole("button", { name: "Ещё" }));
    const sheet = screen.getByRole("dialog", { name: "Все разделы" });
    expect(within(sheet).getAllByRole("link").map((a) => a.textContent)).toEqual(["Соц. паспорт", "Индивидуальная работа"]);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Все разделы" })).not.toBeInTheDocument();
  });

  it("четыре раздела и меньше — без «Ещё»", () => {
    const bar = tabbar("social_pedagogue");
    expect(within(bar).getAllByRole("link")).toHaveLength(4);
    expect(within(bar).queryByRole("button", { name: "Ещё" })).not.toBeInTheDocument();
  });

  it("счётчики на пунктах: дела на сегодня, задачи, проверка", async () => {
    get.mockImplementation(async (path: string) => {
      if (path === "/my-day/counters") return { my_day: 3, my_tasks: 2, review: 0 };
      if (path === "/notifications/unread-count") return { unread: 0 };
      return [];
    });
    renderPage(<Layout><div /></Layout>, { role: "curator" });
    const nav = screen.getByRole("navigation", { name: "Разделы" });
    expect(await within(nav).findByText("3 дел на сегодня")).toBeInTheDocument();
    expect(within(nav).getByText("2 задач требуют внимания")).toBeInTheDocument();
    expect(within(nav).queryByText(/ждут проверки/)).not.toBeInTheDocument();
  });
});

describe("Уведомления (колокольчик)", () => {
  it("показывает число непрочитанных", async () => {
    get.mockImplementation(async (path: string) => (path === "/notifications/unread-count" ? { unread: 3 } : []));
    renderPage(<Layout><div /></Layout>, { role: "curator" });
    expect(await screen.findByText("3")).toBeInTheDocument();
  });

  it("клик по уведомлению о задаче открывает назначение и помечает прочитанным", async () => {
    const user = userEvent.setup();
    const post = vi.mocked(api.post);
    post.mockReset();
    post.mockResolvedValue({});
    get.mockImplementation(async (path: string) => {
      if (path === "/notifications/unread-count") return { unread: 1 };
      return [{ id: 7, kind: "task_assigned", message: "Новая задача «Кружки»", entity_type: "task_assignment", entity_id: "12", created_at: "2026-10-01T09:00:00", read_at: null }];
    });
    renderPage(<Layout><div /></Layout>, { role: "curator" });
    await user.click(await screen.findByRole("button", { name: "Уведомления" }));
    await user.click(await screen.findByText("Новая задача «Кружки»"));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/notifications/7/read"));
    // Переход произошёл: панель закрылась.
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Уведомления" })).not.toBeInTheDocument());
  });

  it("«Прочитать все» сбрасывает счётчик", async () => {
    const user = userEvent.setup();
    const post = vi.mocked(api.post);
    post.mockReset();
    post.mockResolvedValue({ ok: true });
    get.mockImplementation(async (path: string) => {
      if (path === "/notifications/unread-count") return { unread: 2 };
      return [
        { id: 1, kind: "task_due_soon", message: "Скоро срок", entity_type: "task_assignment", entity_id: "1", created_at: "2026-10-01T09:00:00", read_at: null },
        { id: 2, kind: "task_overdue", message: "Просрочена", entity_type: "task_assignment", entity_id: "2", created_at: "2026-10-01T10:00:00", read_at: null },
      ];
    });
    renderPage(<Layout><div /></Layout>, { role: "curator" });
    await user.click(await screen.findByRole("button", { name: "Уведомления" }));
    await user.click(await screen.findByRole("button", { name: "Прочитать все" }));
    expect(post).toHaveBeenCalledWith("/notifications/read-all");
    await waitFor(() => expect(screen.queryByRole("button", { name: "Прочитать все" })).not.toBeInTheDocument());
  });
});

describe("Layout — заголовок страницы", () => {
  it("на каждой странице есть один заголовок первого уровня для экранного диктора и название вкладки", () => {
    renderPage(<Layout><div>содержимое</div></Layout>, { role: "curator", route: "/cabinet" });
    expect(screen.getByRole("heading", { level: 1, name: "Мои группы" })).toBeInTheDocument();
    expect(document.title).toBe("Мои группы — Цифровой куратор");
  });

  it("названия по адресам, включая вложенные", async () => {
    const { pageTitle } = await import("../utils/pageTitle");
    expect(pageTitle("/my-day")).toBe("Мой день");
    expect(pageTitle("/tasks")).toBe("Задачи");
    expect(pageTitle("/tasks/assignment/5")).toBe("Задача");
    expect(pageTitle("/students")).toBe("Студенты");
    expect(pageTitle("/students/12")).toBe("Карточка студента");
    expect(pageTitle("/passport")).toBe("Социальный паспорт");
    expect(pageTitle("/что-то-другое")).toBe("Цифровой куратор");
  });
});
