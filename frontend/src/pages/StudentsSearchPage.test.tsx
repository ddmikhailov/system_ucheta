import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { renderPage } from "../test/utils";
import StudentsSearchPage from "./StudentsSearchPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);

const STUDENTS = [
  { id: 1, full_name: "Алексеев Пётр", group_code: "СА172", status: "studying" },
  { id: 2, full_name: "Андреева Елена", group_code: "ИИ112", status: "academic_leave" },
];

const studentCalls = () => get.mock.calls.map((c) => String(c[0])).filter((p) => p.startsWith("/students"));

beforeEach(() => {
  get.mockReset();
  get.mockImplementation(async (path: string) => {
    if (path.startsWith("/students")) return STUDENTS;
    if (path === "/admin/groups") return [
      { id: 7, code: "СА172", course: 1, is_active: true },
      { id: 8, code: "АРХ-1", course: 1, is_active: false },
    ];
    return [];
  });
});

describe("StudentsSearchPage", () => {
  it("показывает студентов со ссылкой на карточку, группой и статусом", async () => {
    renderPage(<StudentsSearchPage />, { role: "social_pedagogue" });
    const link = await screen.findByRole("link", { name: "Алексеев Пётр" });
    expect(link).toHaveAttribute("href", "/students/1");
    expect(screen.getByText("Учится")).toBeInTheDocument();
    expect(screen.getByText("ИИ112")).toBeInTheDocument();
  });

  it("поиск уходит на сервер с небольшой задержкой и без лишних пробелов", async () => {
    const user = userEvent.setup();
    renderPage(<StudentsSearchPage />, { role: "admin" });
    await screen.findByRole("link", { name: "Алексеев Пётр" });
    await user.type(screen.getByPlaceholderText(/Фамилия, имя или группа/), "  Алек ");
    await waitFor(() => expect(studentCalls().at(-1)).toContain("q=%D0%90%D0%BB%D0%B5%D0%BA")); // «Алек»
    expect(studentCalls().at(-1)).toContain("limit=100");
    // Каждая набранная буква не порождает запрос: их заметно меньше, чем нажатий.
    expect(studentCalls().length).toBeLessThan(6);
  });

  it("фильтр по группе живёт в адресе и попадает в запрос; архивных групп в списке нет", async () => {
    const user = userEvent.setup();
    renderPage(<StudentsSearchPage />, { role: "admin" });
    await screen.findByRole("link", { name: "Алексеев Пётр" });
    expect(screen.queryByRole("option", { name: "АРХ-1" })).not.toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox"), "7");
    await waitFor(() => expect(studentCalls().at(-1)).toContain("group_id=7"));
  });

  it("открытие по ссылке с группой сразу применяет фильтр", async () => {
    renderPage(<StudentsSearchPage />, { route: "/students?group=7", role: "admin" });
    await waitFor(() => expect(studentCalls().some((p) => p.includes("group_id=7"))).toBe(true));
    expect(await screen.findByRole("combobox")).toHaveValue("7");
  });

  it("никого не нашли и ошибка сервера", async () => {
    get.mockImplementation(async (path: string) => (path.startsWith("/students") ? [] : []));
    const { unmount } = renderPage(<StudentsSearchPage />, { role: "admin" });
    expect(await screen.findByText("Никого не найдено.")).toBeInTheDocument();
    unmount();

    get.mockImplementation(async (path: string) => {
      if (path.startsWith("/students")) throw new ApiError(403, "Недостаточно прав");
      return [];
    });
    renderPage(<StudentsSearchPage />, { role: "curator" });
    expect(await screen.findByText("Недостаточно прав")).toBeInTheDocument();
  });

  it("при полной выдаче (100 записей) просит уточнить запрос", async () => {
    const many = Array.from({ length: 100 }, (_, i) => ({ id: i + 1, full_name: `Студент ${i}`, group_code: "СА172", status: "studying" }));
    get.mockImplementation(async (path: string) => (path.startsWith("/students") ? many : []));
    renderPage(<StudentsSearchPage />, { role: "admin" });
    expect(await screen.findByText(/Показаны первые 100/)).toBeInTheDocument();
  });

  it("блок загрузки досье из Excel доступен на странице", async () => {
    renderPage(<StudentsSearchPage />, { role: "admin" });
    expect(await screen.findByRole("button", { name: /Загрузить досье из Excel/ })).toBeInTheDocument();
  });
});
