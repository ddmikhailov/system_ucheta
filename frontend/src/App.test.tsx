import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, setToken } from "./api/client";
import App from "./App";
import { makeUser } from "./test/utils";

vi.mock("./api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

// Тяжёлые страницы заменяем заглушками: здесь проверяется только, кто куда попадает.
vi.mock("./pages/LoginPage", async () => (await import("./test/stub")).stubPage("вход"));
vi.mock("./pages/ChangePasswordPage", async () => (await import("./test/stub")).stubPage("смена пароля"));
vi.mock("./pages/CuratorCabinetPage", async () => (await import("./test/stub")).stubPage("кабинет куратора"));
vi.mock("./pages/MyDayPage", async () => (await import("./test/stub")).stubPage("мой день"));
vi.mock("./pages/DashboardsPage", async () => (await import("./test/stub")).stubPage("витрины"));
vi.mock("./pages/AdminPage", async () => (await import("./test/stub")).stubPage("админка"));
vi.mock("./pages/StudentCardPage", async () => (await import("./test/stub")).stubPage("карточка студента"));
vi.mock("./pages/StudentsSearchPage", async () => (await import("./test/stub")).stubPage("поиск студентов"));
vi.mock("./pages/PassportPage", async () => (await import("./test/stub")).stubPage("соц. паспорт"));
vi.mock("./pages/TasksPage", async () => (await import("./test/stub")).stubPage("задачи"));
vi.mock("./pages/MyTasksPage", async () => (await import("./test/stub")).stubPage("мои задачи"));
vi.mock("./pages/TaskAssignmentPage", async () => (await import("./test/stub")).stubPage("назначение"));
vi.mock("./components/NotificationBell", () => ({ default: () => null }));

const get = vi.mocked(api.get);

function visit(path: string, role: string | null, overrides = {}) {
  window.history.pushState({}, "", path);
  if (role === null) {
    get.mockRejectedValue(new Error("не должно запрашиваться без токена"));
  } else {
    setToken("tok");
    get.mockResolvedValue(makeUser(role, overrides));
  }
  render(<App />);
}

beforeEach(() => {
  get.mockReset();
});

describe("App — стартовая страница по роли", () => {
  it.each([
    ["curator", "мой день"],
    ["deputy_curator", "мой день"],
    ["admin", "витрины"],
    ["dept_head", "витрины"],
    ["tutor", "витрины"],
    ["edu_department", "витрины"],
    ["social_pedagogue", "поиск студентов"],
    ["psychologist", "поиск студентов"],
  ])("%s с «/» попадает на нужную страницу", async (role, page) => {
    visit("/", role);
    expect(await screen.findByText(`страница: ${page}`)).toBeInTheDocument();
  });
});

describe("App — защита маршрутов", () => {
  it("без входа любая страница ведёт на вход", async () => {
    for (const path of ["/my-day", "/cabinet", "/admin", "/tasks", "/passport", "/students/5"]) {
      window.history.pushState({}, "", path);
      const { unmount } = render(<App />);
      expect(await screen.findByText("страница: вход")).toBeInTheDocument();
      unmount();
    }
  });

  it.each(["curator", "deputy_curator", "social_pedagogue", "psychologist"])("%s не попадает в админку", async (role) => {
    visit("/admin", role);
    await waitFor(() => expect(screen.queryByText("страница: админка")).not.toBeInTheDocument());
    expect(await screen.findByText(/страница: (мой день|поиск студентов)/)).toBeInTheDocument();
  });

  it.each(["admin", "tutor", "dept_head", "edu_department"])("%s открывает админку", async (role) => {
    visit("/admin", role);
    expect(await screen.findByText("страница: админка")).toBeInTheDocument();
  });

  it("временный пароль: все страницы ведут на смену пароля", async () => {
    visit("/cabinet", "curator", { must_change_password: true });
    expect(await screen.findByText("страница: смена пароля")).toBeInTheDocument();
  });

  it("страница смены пароля доступна и с временным паролем", async () => {
    visit("/change-password", "curator", { must_change_password: true });
    expect(await screen.findByText("страница: смена пароля")).toBeInTheDocument();
  });

  it("неизвестный адрес — страница 404 со ссылкой на главную", async () => {
    visit("/нет-такой-страницы", "admin");
    expect(await screen.findByText("404")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "На главную" })).toHaveAttribute("href", "/");
  });

  it("новые разделы доступны вошедшим: задачи, мои задачи, паспорт, назначение", async () => {
    visit("/tasks", "admin");
    expect(await screen.findByText("страница: задачи")).toBeInTheDocument();
    // Обёртка Layout с меню: и боковое меню, и нижняя панель телефона.
    expect(within(screen.getByRole("navigation", { name: "Разделы" })).getByRole("link", { name: "Задачи" })).toBeInTheDocument();
  });

  it("куратора по ссылке на «Задачи» отправляет на его главную", async () => {
    visit("/tasks", "curator");
    expect(await screen.findByText("страница: мой день")).toBeInTheDocument();
    expect(screen.queryByText("страница: задачи")).not.toBeInTheDocument();
  });
});
