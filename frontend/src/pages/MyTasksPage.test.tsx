import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { MyAssignmentRow } from "../api/types";
import { renderPage } from "../test/utils";
import MyTasksPage from "./MyTasksPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);

function task(id: number, title: string, status: string, due: string, over: Partial<MyAssignmentRow> = {}): MyAssignmentRow {
  return {
    id, task_id: id, title, collect_mode: "student", group_code: "СА172", due_date: due, status, is_overdue: false,
    is_closed: false, is_locked: false, step_no: 1, step_total: null, filled: 0, total: 25, review_comment: null, ...over,
  };
}

beforeEach(() => {
  get.mockReset();
  // «Сегодня» — воскресенье 4 октября 2026: от него считаются горизонты и «через N дней».
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 9, 4, 10, 0));
});

afterEach(() => vi.useRealTimers());

function section(name: string) {
  return screen.getByRole("region", { name });
}

const titles = (el: HTMLElement) =>
  within(el)
    .getAllByRole("listitem")
    .map((li) => li.querySelector(".inbox-row__title")?.textContent);

describe("MyTasksPage", () => {
  it("раскладывает по горизонтам: горит, на этой неделе, позже, ждёт проверки", async () => {
    get.mockResolvedValue([
      task(1, "На проверке", "submitted", "2026-10-01"),
      task(2, "Через месяц", "new", "2026-11-04"),
      task(3, "Возвращена", "returned", "2026-10-30", { review_comment: "Добавьте фото" }),
      task(4, "Через пять дней", "in_progress", "2026-10-09"),
      task(5, "Просрочена", "in_progress", "2026-10-02", { is_overdue: true }),
      task(6, "Сегодня", "new", "2026-10-04"),
    ]);
    renderPage(<MyTasksPage />, { role: "curator" });
    await screen.findByText("Возвращена");
    expect(titles(section("Горит"))).toEqual(["Просрочена", "Сегодня", "Возвращена"]);
    expect(titles(section("На этой неделе"))).toEqual(["Через пять дней"]);
    expect(titles(section("Позже"))).toEqual(["Через месяц"]);
    expect(titles(section("Ждёт проверки"))).toEqual(["На проверке"]);
  });

  it("замечание проверяющего, относительный срок и заполненность видны в строке", async () => {
    get.mockResolvedValue([
      task(3, "План работы", "returned", "2026-10-04", { collect_mode: "group", review_comment: "Добавьте дату собрания", filled: 2, total: 3 }),
      task(4, "Кружки", "in_progress", "2026-10-09", { filled: 18, total: 25, group_code: "ИИ112" }),
    ]);
    renderPage(<MyTasksPage />, { role: "curator" });
    const plan = (await screen.findByRole("link", { name: "План работы" })).closest("li") as HTMLElement;
    expect(within(plan).getByText("Вернули: «Добавьте дату собрания»")).toBeInTheDocument();
    expect(within(plan).getByText("сегодня")).toBeInTheDocument();
    expect(within(plan).getByText("2 из 3 полей")).toBeInTheDocument();
    expect(within(plan).getByRole("img", { name: "Возвращено" })).toBeInTheDocument();

    const circles = screen.getByRole("link", { name: "Кружки" }).closest("li") as HTMLElement;
    expect(within(circles).getByText("через 5 дней")).toBeInTheDocument();
    expect(within(circles).getByText("пт 09.10")).toBeInTheDocument();
    expect(within(circles).getByText("18 из 25 студентов")).toBeInTheDocument();
    expect(within(circles).getByText("ИИ112")).toBeInTheDocument();
    expect(within(circles).getByText("По каждому студенту")).toBeInTheDocument();
  });

  it("просрочка: красный значок и «просрочено на N дней»", async () => {
    get.mockResolvedValue([task(1, "Флюорография", "in_progress", "2026-10-02", { is_overdue: true, filled: 10 })]);
    renderPage(<MyTasksPage />, { role: "curator" });
    const row = (await screen.findByRole("link", { name: "Флюорография" })).closest("li") as HTMLElement;
    expect(within(row).getByText("просрочено на 2 дня")).toBeInTheDocument();
    expect(within(row).getByRole("img", { name: "Просрочено" })).toBeInTheDocument();
  });

  it("закрытый шаг — в «Позже», без ссылки и с объяснением", async () => {
    get.mockResolvedValue([
      task(1, "Видеовизитка: видео", "new", "2026-10-05", { is_locked: true, step_no: 2, step_total: 2 }),
      task(2, "Видеовизитка: сценарий", "new", "2026-10-20", { step_no: 1, step_total: 2 }),
    ]);
    renderPage(<MyTasksPage />, { role: "curator" });
    await screen.findByText("Видеовизитка: сценарий");
    expect(titles(section("Позже"))).toEqual(["Видеовизитка: сценарий", "Видеовизитка: видео"]);
    expect(screen.queryByRole("link", { name: "Видеовизитка: видео" })).not.toBeInTheDocument();
    expect(screen.getByText("откроется после предыдущего шага")).toBeInTheDocument();
    expect(screen.getByText("шаг 2 из 2")).toBeInTheDocument();
  });

  it("принятые — во вкладке «Готово»", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue([task(1, "Открытая", "new", "2026-10-05"), task(2, "Готовая", "accepted", "2026-09-30", { filled: 25 })]);
    renderPage(<MyTasksPage />, { role: "curator" });
    await screen.findByText("Открытая");
    expect(screen.queryByText("Готовая")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Готово 1" }));
    expect(screen.getByText("Готовая")).toBeInTheDocument();
    expect(screen.getByText("принято")).toBeInTheDocument();
    expect(screen.queryByText("Открытая")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Активные 1" }));
    expect(screen.getByText("Открытая")).toBeInTheDocument();
  });

  it("ссылка ведёт на страницу назначения", async () => {
    get.mockResolvedValue([task(42, "Опрос", "new", "2026-10-05")]);
    renderPage(<MyTasksPage />, { role: "curator" });
    expect(await screen.findByRole("link", { name: "Опрос" })).toHaveAttribute("href", "/tasks/assignment/42");
  });

  it("выборочный режим без отмеченных студентов", async () => {
    get.mockResolvedValue([task(1, "Согласия", "new", "2026-10-10", { collect_mode: "selected", total: 0 })]);
    renderPage(<MyTasksPage />, { role: "curator" });
    expect(await screen.findByText("никто не отмечен")).toBeInTheDocument();
  });

  it("пусто и ошибка загрузки", async () => {
    get.mockResolvedValueOnce([task(1, "Готовая", "accepted", "2026-09-30")]);
    const { unmount } = renderPage(<MyTasksPage />, { role: "curator" });
    expect(await screen.findByText(/Активных задач нет/)).toBeInTheDocument();
    unmount();

    get.mockRejectedValueOnce(new ApiError(500, "Сервер недоступен"));
    renderPage(<MyTasksPage />, { role: "curator" });
    expect(await screen.findByText("Сервер недоступен")).toBeInTheDocument();
  });
});
