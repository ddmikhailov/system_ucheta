import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { TaskTemplate } from "../api/types";
import { scheduleText } from "../constants/tasks";
import TaskTemplatesTab from "./TaskTemplatesTab";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const put = vi.mocked(api.put);
const del = vi.mocked(api.delete);

function tpl(over: Partial<TaskTemplate> = {}): TaskTemplate {
  return {
    id: 1, name: "Ежемесячный отчёт", author_name: "Админ", created_at: "2026-09-01T10:00:00", can_manage: true,
    title: "Отчёт", description: null, collect_mode: "group", reviewer_rule: "dept_head", fields: [],
    scope: { all_groups: true, department_ids: [], courses: [], group_ids: [], exclude_group_ids: [] },
    repeat: "", repeat_day: 1, due_offset_days: 14, next_run: null, last_run_date: null, last_error: null, ...over,
  };
}

beforeEach(() => {
  for (const fn of [get, put, del]) fn.mockReset();
});

describe("scheduleText", () => {
  it("описывает расписание словами", () => {
    expect(scheduleText({ repeat: "", repeat_day: 1, due_offset_days: 14 })).toBe("Не повторяется");
    expect(scheduleText({ repeat: "monthly", repeat_day: 5, due_offset_days: 10 })).toBe("Каждый месяц, 5-го числа; срок — через 10 дн.");
    expect(scheduleText({ repeat: "semester", repeat_day: 1, due_offset_days: 30 })).toMatch(/Каждый семестр \(сентябрь, февраль\), 1-го числа; срок — через 30 дн\./);
  });
});

describe("TaskTemplatesTab", () => {
  it("список: название, режим, автор, расписание, следующий запуск", async () => {
    get.mockResolvedValue([
      tpl({ repeat: "monthly", repeat_day: 5, due_offset_days: 10, next_run: "2026-11-05" }),
      tpl({ id: 2, name: "Разовый", author_name: null }),
    ]);
    render(<TaskTemplatesTab />);
    expect(screen.getByText("Загрузка…")).toBeInTheDocument();
    const rows = (await screen.findAllByRole("row")).slice(1);
    expect(within(rows[0]).getByText("Ежемесячный отчёт")).toBeInTheDocument();
    expect(within(rows[0]).getByText(/Ответ по группе · автор: Админ/)).toBeInTheDocument();
    expect(within(rows[0]).getByText(/Каждый месяц, 5-го числа; срок — через 10 дн\./)).toBeInTheDocument();
    expect(within(rows[0]).getByText("05.11.2026")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Не повторяется")).toBeInTheDocument();
    expect(within(rows[1]).getByText(/автор: —/)).toBeInTheDocument();
  });

  it("пусто и ошибка загрузки", async () => {
    get.mockResolvedValueOnce([]);
    const { unmount } = render(<TaskTemplatesTab />);
    expect(await screen.findByText("Шаблонов пока нет.")).toBeInTheDocument();
    unmount();
    get.mockRejectedValueOnce(new ApiError(403, "Нет доступа"));
    render(<TaskTemplatesTab />);
    expect(await screen.findByText("Нет доступа")).toBeInTheDocument();
  });

  it("пропущенный запуск показывает причину", async () => {
    get.mockResolvedValue([tpl({ repeat: "monthly", last_error: "автор шаблона больше не может создавать задачи" })]);
    render(<TaskTemplatesTab />);
    expect(await screen.findByText(/Последний запуск пропущен: автор шаблона больше не может создавать задачи/)).toBeInTheDocument();
  });

  it("чужой шаблон: управлять нельзя — кнопок нет", async () => {
    get.mockResolvedValue([tpl({ can_manage: false })]);
    render(<TaskTemplatesTab />);
    await screen.findByText("Ежемесячный отчёт");
    expect(screen.queryByRole("button", { name: "Расписание" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Удалить" })).not.toBeInTheDocument();
  });

  it("настройка расписания: поля числа и срока видны только при повторе; запрос уходит с числами", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue([tpl()]);
    put.mockResolvedValue(tpl({ repeat: "monthly" }));
    render(<TaskTemplatesTab />);
    await user.click(await screen.findByRole("button", { name: "Расписание" }));
    expect(screen.queryByLabelText(/Число месяца/)).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Повторять"), "monthly");
    const day = screen.getByLabelText(/Число месяца/);
    await user.clear(day);
    await user.type(day, "5");
    const offset = screen.getByLabelText(/Срок через/);
    await user.clear(offset);
    await user.type(offset, "10");
    get.mockClear();
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(put).toHaveBeenCalledWith("/tasks/templates/1/schedule", { repeat: "monthly", repeat_day: 5, due_offset_days: 10 });
    expect(get).toHaveBeenCalledWith("/tasks/templates"); // список перечитан
    await vi.waitFor(() => expect(screen.queryByText(/^Расписание: /)).not.toBeInTheDocument());
  });

  it("выключение повтора отправляет repeat пустым; ошибка сервера остаётся в форме; «Отмена» закрывает", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue([tpl({ repeat: "monthly", next_run: "2026-11-01" })]);
    render(<TaskTemplatesTab />);
    await user.click(await screen.findByRole("button", { name: "Расписание" }));
    await user.selectOptions(screen.getByLabelText("Повторять"), "");
    put.mockRejectedValueOnce(new ApiError(403, "Расписание меняет автор шаблона или администратор"));
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(put).toHaveBeenCalledWith("/tasks/templates/1/schedule", expect.objectContaining({ repeat: "" }));
    expect(await screen.findByText("Расписание меняет автор шаблона или администратор")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(screen.queryByLabelText("Повторять")).not.toBeInTheDocument();
  });

  it("удаление: подтверждение, запрос, список перечитывается", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue([tpl()]);
    render(<TaskTemplatesTab />);
    const button = await screen.findByRole("button", { name: "Удалить" });
    vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    await user.click(button);
    expect(del).not.toHaveBeenCalled();
    vi.spyOn(window, "confirm").mockReturnValueOnce(true);
    del.mockResolvedValue(undefined);
    get.mockClear();
    await user.click(button);
    expect(del).toHaveBeenCalledWith("/tasks/templates/1");
    await vi.waitFor(() => expect(get).toHaveBeenCalledWith("/tasks/templates"));
  });
});
