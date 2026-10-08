import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, downloadFile } from "../api/client";
import type { MealOverview } from "../api/types";
import { renderPage } from "../test/utils";
import MealsPage from "./MealsPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }, downloadFile: vi.fn() };
});
vi.mock("../components/meals/GroupMealsPanel", () => ({
  default: (p: { groupId: number; viewOnly?: boolean }) => <div>панель группы {p.groupId}, просмотр={String(p.viewOnly)}</div>,
}));

const get = vi.mocked(api.get);
const download = vi.mocked(downloadFile);

const OVERVIEW: MealOverview = {
  week_start: "2030-01-14",
  deadline: "2030-01-10T16:00:00",
  dates: ["2030-01-14", "2030-01-15"],
  totals: { "2030-01-14": 40, "2030-01-15": 40 },
  rows: [
    { study_group_id: 1, code: "СА172", course: 1, department_id: 1, department_name: "Диджитал", curator_name: "Иванова А.", eaters: 24, attendance_percent: 90,
      status: "submitted", submitted_at: "2030-01-09T10:00:00", days: [{ date: "2030-01-14", count: 22, source: "submitted" }, { date: "2030-01-15", count: 20, source: "edited" }] },
    { study_group_id: 2, code: "ИИ212", course: 2, department_id: 2, department_name: "Моссовет", curator_name: null, eaters: 20, attendance_percent: null,
      status: "forecast", submitted_at: null, days: [{ date: "2030-01-14", count: 18, source: "forecast" }, { date: "2030-01-15", count: 18, source: "forecast" }] },
    { study_group_id: 3, code: "ИТ301", course: 3, department_id: 1, department_name: "Диджитал", curator_name: "Петров П.", eaters: 10, attendance_percent: 70,
      status: "pending", submitted_at: null, days: [{ date: "2030-01-14", count: 9, source: "forecast" }, { date: "2030-01-15", count: 9, source: "forecast" }] },
  ],
};

beforeEach(() => {
  get.mockReset();
  download.mockReset();
  download.mockResolvedValue(undefined);
  get.mockResolvedValue(OVERVIEW);
});

const codes = () => Array.from(document.querySelectorAll(".dash-table tbody tr td:first-child")).map((td) => td.textContent);

describe("MealsPage — свод питания", () => {
  it("показывает группы, числа по дням, итоги и сводку по подаче", async () => {
    renderPage(<MealsPage />, { role: "meal_manager" });
    expect(await screen.findByText("СА172")).toBeInTheDocument();
    expect(codes()).toEqual(["СА172", "ИИ212", "ИТ301"]);
    expect(get).toHaveBeenCalledWith(expect.stringMatching(/^\/meals\/overview\?week_start=\d{4}-\d{2}-\d{2}$/));
    expect(screen.getByText(/Подано: 1 из 3/)).toBeInTheDocument();
    expect(screen.getByText(/по прогнозу: 1/)).toBeInTheDocument();
    const foot = document.querySelector("tfoot") as HTMLElement;
    expect(within(foot).getByText("54")).toBeInTheDocument(); // питающихся всего
  });

  it("фильтры: отделение, статус, поиск по куратору; итоги пересчитываются по видимым строкам", async () => {
    const user = userEvent.setup();
    renderPage(<MealsPage />, { role: "meal_manager" });
    await screen.findByText("СА172");
    await user.selectOptions(screen.getByLabelText("Отделение"), "1");
    expect(codes()).toEqual(["СА172", "ИТ301"]);
    await user.selectOptions(screen.getByLabelText("Статус подачи"), "pending");
    expect(codes()).toEqual(["ИТ301"]);
    expect(screen.getByRole("status")).toHaveTextContent("Показано 1 из 3");
    await user.click(screen.getByRole("button", { name: "Сбросить фильтры" }));
    await user.type(screen.getByLabelText("Поиск по группе или куратору"), "петров");
    expect(codes()).toEqual(["ИТ301"]);
  });

  it("сортировка по числу на день", async () => {
    const user = userEvent.setup();
    renderPage(<MealsPage />, { role: "meal_manager" });
    await screen.findByText("СА172");
    const header = screen.getAllByRole("button").find((b) => b.textContent?.includes("пн"))!;
    await user.click(header);
    expect(codes()).toEqual(["ИТ301", "ИИ212", "СА172"]);
    await user.click(header);
    expect(codes()).toEqual(["СА172", "ИИ212", "ИТ301"]);
  });

  it("клик по группе открывает панель только для просмотра", async () => {
    const user = userEvent.setup();
    renderPage(<MealsPage />, { role: "meal_manager" });
    await user.click(await screen.findByText("ИИ212"));
    expect(await screen.findByText("панель группы 2, просмотр=true")).toBeInTheDocument();
  });

  it("листает недели и выгружает Excel за выбранную неделю и отделение", async () => {
    const user = userEvent.setup();
    renderPage(<MealsPage />, { role: "meal_manager" });
    await screen.findByText("СА172");
    await user.click(screen.getByRole("button", { name: "Предыдущая неделя" }));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    await user.selectOptions(screen.getByLabelText("Отделение"), "2");
    await user.click(screen.getByRole("button", { name: "Экспорт в Excel" }));
    expect(download).toHaveBeenCalledWith(expect.stringMatching(/^\/meals\/export\?week_start=\d{4}-\d{2}-\d{2}&department_id=2$/), expect.stringMatching(/^pitanie_/));
  });

  it("пустая неделя объяснена", async () => {
    get.mockResolvedValue({ ...OVERVIEW, rows: [], dates: [], totals: {} });
    renderPage(<MealsPage />, { role: "admin" });
    expect(await screen.findByText("На эту неделю данных нет.")).toBeInTheDocument();
  });
});
