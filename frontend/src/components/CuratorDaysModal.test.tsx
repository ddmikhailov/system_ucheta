import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { CuratorDaysRead } from "../api/types";
import CuratorDaysModal from "./CuratorDaysModal";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);

function data(over: Partial<CuratorDaysRead> = {}): CuratorDaysRead {
  return {
    study_group_id: 7, group_code: "СА172", responsible_name: "Иванова Анна",
    date_from: "2026-09-28", date_to: "2026-10-02",
    on_time: 2, late: 1, missed: 1, total_study_days: 4, average_on_time_submission: "09:15",
    days: [
      { date: "2026-09-28", status: "on_time", submitted_at_local: "2026-09-28T09:10:00", submitted_by: "Иванова Анна", first_period: 2, days_late: null },
      { date: "2026-09-29", status: "late", submitted_at_local: "2026-10-01T14:05:00", submitted_by: "Петров П.", first_period: null, days_late: 2 },
      { date: "2026-09-30", status: "missed", submitted_at_local: null, submitted_by: null, first_period: null, days_late: null },
    ],
    ...over,
  };
}

const open = (onClose = vi.fn()) => {
  render(<CuratorDaysModal studyGroupId={7} dateFrom="2026-09-28" dateTo="2026-10-02" onClose={onClose} />);
  return onClose;
};

beforeEach(() => get.mockReset());

describe("CuratorDaysModal", () => {
  it("запрашивает дни группы за период и показывает итоги", async () => {
    get.mockResolvedValue(data());
    open();
    expect(screen.getByText("Загрузка…")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "СА172 — Иванова Анна" })).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/dashboards/curator-discipline/7/days?date_from=2026-09-28&date_to=2026-10-02");
    expect(screen.getByText(/вовремя 2, задним числом 1, не сдано 1 из 4 учебных дней/)).toBeInTheDocument();
    expect(screen.getByText(/В среднем день сдаётся около 09:15/)).toBeInTheDocument();
  });

  it("строки: статус, «+N дн.», время (дата только если сдано не в тот же день), кто сдал, пара", async () => {
    get.mockResolvedValue(data());
    open();
    await screen.findByText("Петров П.");
    const rows = screen.getAllByRole("row").slice(1);
    const cells = (r: HTMLElement) => within(r).getAllByRole("cell").map((c) => c.textContent);
    expect(cells(rows[0])).toEqual(["28.09.2026 пн", "вовремя", "09:10", "Иванова Анна", "2"]);
    expect(cells(rows[1])).toEqual(["29.09.2026 вт", "задним числом (+2 дн.)", "01.10 14:05", "Петров П.", "—"]);
    expect(cells(rows[2])).toEqual(["30.09.2026 ср", "не сдано", "—", "—", "—"]);
    expect(rows[2]).toHaveClass("not-submitted-row");
    expect(rows[0]).not.toHaveClass("not-submitted-row");
  });

  it("нет куратора и нет среднего времени — без лишних фраз", async () => {
    get.mockResolvedValue(data({ responsible_name: null, average_on_time_submission: null }));
    open();
    expect(await screen.findByRole("heading", { name: "СА172 — нет куратора" })).toBeInTheDocument();
    expect(screen.queryByText(/В среднем/)).not.toBeInTheDocument();
  });

  it("нет учебных дней в периоде — пояснение", async () => {
    get.mockResolvedValue(data({ days: [], on_time: 0, late: 0, missed: 0, total_study_days: 0 }));
    open();
    expect(await screen.findByText("За выбранный период нет учебных дней.")).toBeInTheDocument();
  });

  it("ошибка сервера и сбой сети", async () => {
    get.mockRejectedValueOnce(new ApiError(403, "Нет доступа к группе"));
    const { unmount } = render(<CuratorDaysModal studyGroupId={7} dateFrom="a" dateTo="b" onClose={vi.fn()} />);
    expect(await screen.findByText("Нет доступа к группе")).toBeInTheDocument();
    unmount();
    get.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    render(<CuratorDaysModal studyGroupId={7} dateFrom="a" dateTo="b" onClose={vi.fn()} />);
    expect(await screen.findByText("Ошибка загрузки")).toBeInTheDocument();
  });

  it("закрывается кнопкой, Escape и щелчком по фону, но не по самому окну", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue(data());
    const onClose = open();
    await screen.findByText("Петров П.");
    await user.click(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Закрыть" }));
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("dialog").parentElement!);
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it("при смене группы показывает загрузку, а не данные прежней", async () => {
    get.mockResolvedValueOnce(data());
    const { rerender } = render(<CuratorDaysModal studyGroupId={7} dateFrom="a" dateTo="b" onClose={vi.fn()} />);
    await screen.findByText("Петров П.");
    get.mockReturnValueOnce(new Promise(() => {}));
    rerender(<CuratorDaysModal studyGroupId={8} dateFrom="a" dateTo="b" onClose={vi.fn()} />);
    expect(screen.getByText("Загрузка…")).toBeInTheDocument();
    expect(screen.queryByText("Петров П.")).not.toBeInTheDocument();
  });
});
