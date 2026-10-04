import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
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
  return { id, task_id: id, title, collect_mode: "student", group_code: "СА172", due_date: due, status, is_overdue: false, is_closed: false, ...over };
}

beforeEach(() => get.mockReset());

const titlesInOrder = () =>
  screen.getAllByRole("link").map((a) => a.textContent);

describe("MyTasksPage", () => {
  it("сначала то, что требует действий: возвращённые, потом в работе, не начатые, на проверке; внутри — по сроку", async () => {
    get.mockResolvedValue([
      task(1, "На проверке", "submitted", "2026-10-01"),
      task(2, "Не начата поздняя", "new", "2026-10-20"),
      task(3, "Возвращена", "returned", "2026-10-30"),
      task(4, "Не начата ранняя", "new", "2026-10-05"),
      task(5, "В работе", "in_progress", "2026-10-25"),
    ]);
    renderPage(<MyTasksPage />, { role: "curator" });
    await screen.findByText("Возвращена");
    expect(titlesInOrder()).toEqual(["Возвращена", "В работе", "Не начата ранняя", "Не начата поздняя", "На проверке"]);
  });

  it("принятые спрятаны под кнопкой и раскрываются по клику", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue([task(1, "Открытая", "new", "2026-10-05"), task(2, "Готовая", "accepted", "2026-09-30")]);
    renderPage(<MyTasksPage />, { role: "curator" });
    await screen.findByText("Открытая");
    expect(screen.queryByText("Готовая")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Принятые (1)" }));
    expect(screen.getByText("Готовая")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Скрыть принятые" }));
    expect(screen.queryByText("Готовая")).not.toBeInTheDocument();
  });

  it("помечает просрочку и показывает срок в формате ДД.ММ.ГГГГ, режим и группу", async () => {
    get.mockResolvedValue([task(1, "Кружки", "in_progress", "2026-10-02", { is_overdue: true, collect_mode: "group", group_code: "ИИ112" })]);
    renderPage(<MyTasksPage />, { role: "curator" });
    const row = (await screen.findByRole("link", { name: "Кружки" })).closest("tr") as HTMLElement;
    expect(within(row).getByText(/02\.10\.2026/)).toBeInTheDocument();
    expect(within(row).getByText("просрочено")).toBeInTheDocument();
    expect(within(row).getByText("Ответ по группе")).toBeInTheDocument();
    expect(within(row).getByText("ИИ112")).toBeInTheDocument();
    expect(within(row).getByText("В работе")).toBeInTheDocument();
  });

  it("ссылка ведёт на страницу назначения", async () => {
    get.mockResolvedValue([task(42, "Опрос", "new", "2026-10-05")]);
    renderPage(<MyTasksPage />, { role: "curator" });
    expect(await screen.findByRole("link", { name: "Опрос" })).toHaveAttribute("href", "/tasks/assignment/42");
  });

  it("нет открытых задач — сообщение, а принятые остаются доступны", async () => {
    get.mockResolvedValue([task(1, "Готовая", "accepted", "2026-09-30")]);
    renderPage(<MyTasksPage />, { role: "curator" });
    expect(await screen.findByText("Активных задач нет.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Принятые (1)" })).toBeInTheDocument();
  });

  it("совсем пусто и ошибка загрузки", async () => {
    get.mockResolvedValueOnce([]);
    const { unmount } = renderPage(<MyTasksPage />, { role: "curator" });
    expect(await screen.findByText("Активных задач нет.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Принятые/ })).not.toBeInTheDocument();
    unmount();

    get.mockRejectedValueOnce(new ApiError(500, "Сервер недоступен"));
    renderPage(<MyTasksPage />, { role: "curator" });
    expect(await screen.findByText("Сервер недоступен")).toBeInTheDocument();
  });
});
