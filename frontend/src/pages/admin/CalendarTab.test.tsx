import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../../api/client";
import { renderPage } from "../../test/utils";
import CalendarTab from "./CalendarTab";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const put = vi.mocked(api.put);
const del = vi.mocked(api.delete);

beforeEach(() => {
  for (const fn of [get, put, del]) fn.mockReset();
  get.mockImplementation(async (path: string) => {
    if (path === "/admin/groups") return [{ id: 7, code: "СА172", course: 1, is_active: true }];
    if (path.startsWith("/admin/calendar/group-overrides")) return [{ study_group_id: 7, date: "2026-10-15", day_type: "remote" }];
    if (path.startsWith("/admin/calendar")) return [{ date: "2026-11-04", day_type: "holiday" }];
    return [];
  });
  put.mockResolvedValue({});
});

const rangeStart = () => screen.getByTitle("Дата (начало диапазона)");
const rangeEnd = () => screen.getByTitle(/Конец диапазона/);

describe("CalendarTab — общий календарь", () => {
  it("диапазон каникул сохраняется по дням без сдвига на сутки (в поясе UTC+3)", async () => {
    const user = userEvent.setup();
    renderPage(<CalendarTab canEdit canEditGroups />);
    await screen.findByText("04.11.2026");
    fireEvent.change(rangeStart(), { target: { value: "2026-10-30" } });
    fireEvent.change(rangeEnd(), { target: { value: "2026-11-02" } });
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(4));
    // Раньше полночь по местному времени превращалась в предыдущий день: 29.10 вместо 30.10.
    expect(put.mock.calls.map((c) => (c[1] as { date: string }).date)).toEqual([
      "2026-10-30", "2026-10-31", "2026-11-01", "2026-11-02",
    ]);
    expect(put.mock.calls.every((c) => c[0] === "/admin/calendar" && (c[1] as { day_type: string }).day_type === "holiday")).toBe(true);
  });

  it("без конца диапазона сохраняется один день выбранного типа", async () => {
    const user = userEvent.setup();
    renderPage(<CalendarTab canEdit canEditGroups />);
    await screen.findByText("04.11.2026");
    fireEvent.change(rangeStart(), { target: { value: "2026-12-31" } });
    await user.selectOptions(screen.getAllByRole("combobox")[0], "vacation");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put).toHaveBeenCalledWith("/admin/calendar", { date: "2026-12-31", day_type: "vacation" });
  });

  it("диапазон через конец года и високосный февраль", async () => {
    const user = userEvent.setup();
    renderPage(<CalendarTab canEdit canEditGroups />);
    await screen.findByText("04.11.2026");
    fireEvent.change(rangeStart(), { target: { value: "2027-12-30" } });
    fireEvent.change(rangeEnd(), { target: { value: "2028-01-02" } });
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(4));
    expect(put.mock.calls.map((c) => (c[1] as { date: string }).date)).toEqual([
      "2027-12-30", "2027-12-31", "2028-01-01", "2028-01-02",
    ]);
  });

  it("ошибка на одном из дней прерывает сохранение и показывается", async () => {
    const user = userEvent.setup();
    put.mockResolvedValueOnce({}).mockRejectedValueOnce(new ApiError(403, "Недостаточно прав"));
    renderPage(<CalendarTab canEdit canEditGroups />);
    await screen.findByText("04.11.2026");
    fireEvent.change(rangeStart(), { target: { value: "2026-10-30" } });
    fireEvent.change(rangeEnd(), { target: { value: "2026-11-02" } });
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(await screen.findByText("Недостаточно прав")).toBeInTheDocument();
    expect(put).toHaveBeenCalledTimes(2);
  });

  it("удаление исключения вызывает DELETE по дате", async () => {
    const user = userEvent.setup();
    del.mockResolvedValue({});
    renderPage(<CalendarTab canEdit canEditGroups />);
    const row = (await screen.findByText("04.11.2026")).closest("tr") as HTMLElement;
    await user.click(row.querySelector("button") as HTMLButtonElement);
    expect(del).toHaveBeenCalledWith("/admin/calendar/2026-11-04");
  });
});

describe("CalendarTab — права", () => {
  it("зав. отделением правит только исключения групп: общий календарь только для чтения", async () => {
    renderPage(<CalendarTab canEdit={false} canEditGroups />, { role: "dept_head" });
    await screen.findByText("04.11.2026");
    expect(screen.queryByText("Добавить исключение для всего колледжа")).not.toBeInTheDocument();
    expect(screen.getByText("Добавить исключение для выбранной группы")).toBeInTheDocument();
  });

  it("исключение для группы сохраняется с id выбранной группы", async () => {
    const user = userEvent.setup();
    renderPage(<CalendarTab canEdit={false} canEditGroups />, { role: "dept_head" });
    await screen.findByText("15.10.2026");
    await user.click(screen.getByRole("button", { name: "Сохранить для группы" }));
    await waitFor(() => expect(put).toHaveBeenCalledWith("/admin/calendar/group-overrides", expect.objectContaining({ study_group_id: 7, day_type: "remote" })));
  });

  it("только просмотр: форм добавления нет вообще", async () => {
    renderPage(<CalendarTab canEdit={false} canEditGroups={false} />, { role: "edu_department" });
    await screen.findByText("04.11.2026");
    expect(screen.queryByRole("button", { name: "Сохранить" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Сохранить для группы" })).not.toBeInTheDocument();
  });
});
