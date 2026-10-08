import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../../api/client";
import type { GroupMeals, MealWeek } from "../../api/types";
import { renderPage } from "../../test/utils";
import GroupMealsPanel from "./GroupMealsPanel";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);
const put = vi.mocked(api.put);

function week(over: Partial<MealWeek> = {}): MealWeek {
  return {
    week_start: "2030-01-14", status: "pending", deadline: "2030-01-10T16:00:00", submitted_count: null, submitted_at: null, forecast: 17,
    days: [
      { date: "2030-01-14", count: 17, source: "forecast", open: true, cutoff: "2030-01-11T10:00:00" },
      { date: "2030-01-15", count: 17, source: "forecast", open: false, cutoff: "2030-01-14T10:00:00" },
    ],
    ...over,
  };
}

function meals(over: Partial<GroupMeals> = {}): GroupMeals {
  return {
    study_group_id: 7, code: "СА172", funding: null, can_edit: true, eaters: 2, attendance_percent: 80, hint: 2,
    students: [
      { student_id: 1, full_name: "Алексеев Пётр", eats: true, locked_reason: null },
      { student_id: 2, full_name: "Борисов Иван", eats: true, locked_reason: null },
      { student_id: 3, full_name: "Васильев Олег", eats: false, locked_reason: "Обучение на договорной основе" },
    ],
    weeks: [week({ week_start: "2030-01-07" }), week()],
    ...over,
  };
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  put.mockReset();
});

function open(data: GroupMeals, viewOnly = false) {
  get.mockResolvedValue(data);
  renderPage(<GroupMealsPanel groupId={7} viewOnly={viewOnly} />, { role: "curator" });
}

describe("GroupMealsPanel — куратор", () => {
  it("показывает питающихся, подсказку по посещаемости и срок подачи; договорник заблокирован", async () => {
    open(meals());
    expect(await screen.findByText(/Подайте питание до 10\.01 16:00/)).toBeInTheDocument();
    expect(screen.getByText(/Средняя посещаемость группы за последнюю неделю — 80%/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Питается: Алексеев Пётр" })).toBeChecked();
    const locked = screen.getByRole("checkbox", { name: "Питается: Васильев Олег" });
    expect(locked).toBeDisabled();
    expect(screen.getByText(/Обучение на договорной основе/)).toBeInTheDocument();
    expect(screen.getByLabelText("Итоговое число питающихся на неделю")).toHaveValue(2);
  });

  it("отметка «не питается» уходит на сервер и список перечитывается", async () => {
    const user = userEvent.setup();
    open(meals());
    put.mockResolvedValue(undefined);
    await user.click(await screen.findByRole("checkbox", { name: "Питается: Борисов Иван" }));
    expect(put).toHaveBeenCalledWith("/meals/groups/7/students/2", { eats: false });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  });

  it("«Подать питание» отправляет неделю и итоговое число", async () => {
    const user = userEvent.setup();
    open(meals());
    post.mockResolvedValue(week({ status: "submitted", submitted_count: 1, submitted_at: "2030-01-09T12:00:00" }));
    const total = await screen.findByLabelText("Итоговое число питающихся на неделю");
    await user.clear(total);
    await user.type(total, "1");
    await user.click(screen.getByRole("button", { name: "Подать питание" }));
    expect(post).toHaveBeenCalledWith("/meals/groups/7/week", { week_start: "2030-01-14", count: 1 });
    expect(await screen.findByText(/Подано: 1/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Подать заново" })).toBeInTheDocument();
  });

  it("день можно поправить, пока он открыт; закрытый день — только число", async () => {
    const user = userEvent.setup();
    open(meals());
    put.mockResolvedValue(week({ days: [
      { date: "2030-01-14", count: 15, source: "edited", open: true, cutoff: "2030-01-11T10:00:00" },
      { date: "2030-01-15", count: 17, source: "forecast", open: false, cutoff: "2030-01-14T10:00:00" },
    ] }));
    const input = await screen.findByLabelText("Число на 14.01.2030");
    expect(screen.queryByLabelText("Число на 15.01.2030")).not.toBeInTheDocument();
    expect(screen.getByText("закрыто")).toBeInTheDocument();
    await user.clear(input);
    await user.type(input, "15");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(put).toHaveBeenCalledWith("/meals/groups/7/day", { date: "2030-01-14", count: 15 });
    expect(await screen.findByRole("button", { name: "Сбросить" })).toBeInTheDocument();
  });

  it("подсказку можно подставить одной кнопкой", async () => {
    const user = userEvent.setup();
    open(meals({ hint: 1 }));
    await user.click(await screen.findByRole("button", { name: "Подставить 1" }));
    expect(screen.getByLabelText("Итоговое число питающихся на неделю")).toHaveValue(1);
  });

  it("после срока объясняет, что идёт прогноз", async () => {
    open(meals({ weeks: [week({ week_start: "2030-01-07" }), week({ status: "forecast" })] }));
    expect(await screen.findByText(/Срок подачи прошёл/)).toBeInTheDocument();
  });

  it("договорная группа: питания нет, подачи нет", async () => {
    open(meals({ funding: "contract", eaters: 0, weeks: [] }));
    expect(await screen.findByText(/Группа на договорной основе/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Подать питание" })).not.toBeInTheDocument();
  });

  it("ошибка сервера при подаче показывается уведомлением, а не молчит", async () => {
    const user = userEvent.setup();
    open(meals());
    post.mockRejectedValue(new ApiError(409, "Приём питания на эту неделю закрыт"));
    await user.click(await screen.findByRole("button", { name: "Подать питание" }));
    await waitFor(() => expect(post).toHaveBeenCalled());
  });
});

describe("GroupMealsPanel — просмотр (ответственная по питанию)", () => {
  it("список и числа видны, но никаких полей и кнопок правки", async () => {
    open(meals({ can_edit: false }), true);
    expect(await screen.findByText("Алексеев Пётр")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Подать/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Итоговое число питающихся на неделю")).not.toBeInTheDocument();
    for (const box of screen.getAllByRole("checkbox")) expect(box).toBeDisabled();
    expect(within(screen.getByRole("table")).getByText("закрыто")).toBeInTheDocument();
  });
});
