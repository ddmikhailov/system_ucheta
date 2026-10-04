import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { StudentDayAttendance, StudentMonthAttendance } from "../api/types";
import StudentMonthAttendanceView from "./StudentMonthAttendance";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);

function day(date: string, over: Partial<StudentDayAttendance> = {}): StudentDayAttendance {
  return {
    date, day_type: "study_day", status: "present", group_code: "СА172", mark_code: null, mark_name: null,
    counts_as_present: null, is_excused: null, comment: null, basis_reference: null, ...over,
  };
}

function month(over: Partial<StudentMonthAttendance> = {}): StudentMonthAttendance {
  return {
    student_id: 5, year: 2026, month: 10, first_month: "2026-09",
    summary: { study_days: 4, present: 1, absent: 2, absent_excused: 1, absent_unexcused: 1, late: 1, not_submitted: 1, percent: 25, by_code: {} },
    days: [
      day("2026-10-01"),
      day("2026-10-02", { status: "mark", mark_code: "н", mark_name: "Неуважительная", counts_as_present: false, comment: "прогул", basis_reference: "акт 3" }),
      day("2026-10-03", { status: "mark", mark_code: "оп", mark_name: "Опоздание", counts_as_present: true }),
      day("2026-10-04", { day_type: "weekend", status: "none" }),
      day("2026-10-05", { status: "not_submitted" }),
    ],
    ...over,
  };
}

// Сегодня — 15 октября 2026; подменяем только Date, таймеры остаются настоящими.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 9, 15, 12, 0, 0));
  get.mockReset();
});
afterEach(() => vi.useRealTimers());

const rows = () => screen.getAllByRole("row").slice(1);

describe("StudentMonthAttendanceView", () => {
  it("открывается на текущем месяце и запрашивает его у сервера", async () => {
    get.mockResolvedValue(month());
    render(<StudentMonthAttendanceView studentId={5} />);
    expect(screen.getByText(/^Октябрь 2026 г./)).toBeInTheDocument();
    expect(await screen.findByText("01.10 чт")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/students/5/attendance?year=2026&month=10");
  });

  it("сводка: уважительные/неуважительные, опоздания, не сданные группой, процент", async () => {
    get.mockResolvedValue(month());
    render(<StudentMonthAttendanceView studentId={5} />);
    expect(
      await screen.findByText(/Учебных дней: 4 · присутствовал: 1 · отсутствовал: 2 \(уваж\. 1, неуваж\. 1\) · опозданий: 1 · не сдано группой: 1 · посещаемость: 25%/)
    ).toBeInTheDocument();
  });

  it("сводка без отсутствий, без несданных дней и без процента — лишних кусков нет", async () => {
    get.mockResolvedValue(
      month({ summary: { study_days: 0, present: 0, absent: 0, absent_excused: 0, absent_unexcused: 0, late: 0, not_submitted: 0, percent: null, by_code: {} }, days: [] })
    );
    render(<StudentMonthAttendanceView studentId={5} />);
    const text = (await screen.findByText(/Учебных дней: 0/)).textContent!;
    expect(text).not.toMatch(/уваж|не сдано группой|посещаемость:/);
    expect(screen.getByText("За этот месяц нет учебных дней.")).toBeInTheDocument();
  });

  it("строки: присутствовал, отметка с комментарием и основанием, день не сдан; выходной скрыт", async () => {
    get.mockResolvedValue(month());
    render(<StudentMonthAttendanceView studentId={5} />);
    await screen.findByText("01.10 чт");
    const r = rows();
    expect(r).toHaveLength(4);
    const cells = (row: HTMLElement) => within(row).getAllByRole("cell").map((c) => c.textContent);
    expect(cells(r[0])).toEqual(["01.10 чт", "Присутствовал", "—", "—"]);
    expect(cells(r[1])).toEqual(["02.10 пт", "Н — Неуважительная", "прогул", "акт 3"]);
    expect(cells(r[3])).toEqual(["05.10 пн", "День не сдан группой", "—", "—"]);
    // подсветка: неуважительное отсутствие и несданный день; опоздание (засчитано как присутствие) — без
    expect(r[1]).toHaveClass("day-absent");
    expect(r[2]).not.toHaveClass("day-absent");
    expect(r[3]).toHaveClass("day-not-submitted");
  });

  it("«показывать выходные» добавляет нерабочие дни с подписью типа", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue(
      month({ days: [day("2026-10-03", { day_type: "holiday", status: "none" }), day("2026-10-04", { day_type: "not_enrolled", status: "none" }), day("2026-10-05")] })
    );
    render(<StudentMonthAttendanceView studentId={5} />);
    await screen.findByText("05.10 пн");
    expect(rows()).toHaveLength(1);
    await user.click(screen.getByLabelText(/показывать выходные/));
    const r = rows();
    expect(r).toHaveLength(3);
    expect(within(r[0]).getByText("праздник")).toBeInTheDocument();
    expect(within(r[1]).getByText("не числился")).toBeInTheDocument();
    expect(r[0]).toHaveClass("day-nonworking");
  });

  it("листание назад запрашивает прошлый месяц; дальше первого месяца студента — нельзя", async () => {
    const user = userEvent.setup();
    get.mockImplementation(async (path: string) =>
      path.endsWith("month=9") ? month({ month: 9, days: [day("2026-09-01")] }) : month()
    );
    render(<StudentMonthAttendanceView studentId={5} />);
    await screen.findByText("01.10 чт");
    const prev = screen.getByRole("button", { name: "Предыдущий месяц" });
    expect(prev).toBeEnabled();
    await user.click(prev);
    expect(await screen.findByText(/^Сентябрь 2026 г./)).toBeInTheDocument();
    expect(get).toHaveBeenLastCalledWith("/students/5/attendance?year=2026&month=9");
    await screen.findByText("01.09 вт");
    expect(screen.getByRole("button", { name: "Предыдущий месяц" })).toBeDisabled(); // first_month = 2026-09
    await user.click(screen.getByRole("button", { name: "Следующий месяц" }));
    expect(await screen.findByText(/^Октябрь 2026 г./)).toBeInTheDocument();
  });

  it("в текущем месяце «вперёд» недоступно (будущее не листается)", async () => {
    get.mockResolvedValue(month());
    render(<StudentMonthAttendanceView studentId={5} />);
    await screen.findByText("01.10 чт");
    expect(screen.getByRole("button", { name: "Следующий месяц" })).toBeDisabled();
  });

  it("переход через границу года: январь ← декабрь", async () => {
    const user = userEvent.setup();
    vi.setSystemTime(new Date(2027, 0, 20, 12, 0, 0));
    get.mockResolvedValue(month({ first_month: "2026-09", year: 2027, month: 1, days: [] }));
    render(<StudentMonthAttendanceView studentId={5} />);
    expect(screen.getByText(/^Январь 2027 г./)).toBeInTheDocument();
    await screen.findByText("За этот месяц нет учебных дней.");
    await user.click(screen.getByRole("button", { name: "Предыдущий месяц" }));
    expect(await screen.findByText(/^Декабрь 2026 г./)).toBeInTheDocument();
    expect(get).toHaveBeenLastCalledWith("/students/5/attendance?year=2026&month=12");
  });

  it("пока месяц грузится — «Загрузка…», данные прошлого месяца не показываются", async () => {
    const user = userEvent.setup();
    get.mockResolvedValueOnce(month());
    render(<StudentMonthAttendanceView studentId={5} />);
    await screen.findByText("01.10 чт");
    get.mockReturnValueOnce(new Promise(() => {}));
    await user.click(screen.getByRole("button", { name: "Предыдущий месяц" }));
    expect(screen.getByText("Загрузка…")).toBeInTheDocument();
    expect(screen.queryByText("01.10 чт")).not.toBeInTheDocument();
  });

  it("ошибка сервера и сбой сети", async () => {
    get.mockRejectedValueOnce(new ApiError(403, "Нет доступа к студенту"));
    const { unmount } = render(<StudentMonthAttendanceView studentId={5} />);
    expect(await screen.findByText("Нет доступа к студенту")).toBeInTheDocument();
    unmount();
    get.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    render(<StudentMonthAttendanceView studentId={5} />);
    expect(await screen.findByText("Ошибка загрузки")).toBeInTheDocument();
  });
});
