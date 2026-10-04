import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { IndividualWorkGroup, IndividualWorkRow } from "../api/types";
import { renderPage } from "../test/utils";
import IndividualWorkPage from "./IndividualWorkPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);

function row(id: number, name: string, over: Partial<IndividualWorkRow> = {}): IndividualWorkRow {
  return {
    student_id: id, full_name: name, risk_streak: 0, is_risk: false, work_count: 0, last_work_on: null,
    next_follow_up_on: null, follow_up_overdue: false, needs_attention: false, ...over,
  };
}

function group(id: number, code: string, rows: IndividualWorkRow[]): IndividualWorkGroup {
  return { group_id: id, group_code: code, no_work_days: 14, rows };
}

const GROUPS = [{ id: 7, code: "СА172", course: 1 }, { id: 8, code: "ИИ212", course: 2 }];

function mock(byGroup: Record<number, IndividualWorkGroup>, groups = GROUPS) {
  get.mockImplementation(async (path: string) => {
    if (path === "/individual-work/groups") return groups;
    const m = path.match(/^\/individual-work\/groups\/(\d+)$/);
    if (m) return byGroup[Number(m[1])];
    throw new Error(`неожиданный запрос ${path}`);
  });
}

beforeEach(() => {
  get.mockReset();
});

describe("IndividualWorkPage", () => {
  it("открывает первую группу и показывает студентов: серия, работа, срок возврата, статус", async () => {
    mock({
      7: group(7, "СА172", [
        row(1, "Алексеев Пётр", { is_risk: true, risk_streak: 5, needs_attention: true }),
        row(2, "Андреева Елена", { is_risk: true, risk_streak: 4, work_count: 2, last_work_on: "2026-10-01", next_follow_up_on: "2026-09-30", follow_up_overdue: true }),
        row(3, "Борисов Иван", { work_count: 1, last_work_on: "2026-08-20", next_follow_up_on: "2026-10-20" }),
      ]),
    });
    renderPage(<IndividualWorkPage />, { role: "curator" });
    const first = (await screen.findByRole("link", { name: "Алексеев Пётр" })).closest("tr") as HTMLElement;
    expect(get).toHaveBeenCalledWith("/individual-work/groups/7");
    expect(within(first).getByText("5")).toBeInTheDocument();
    expect(within(first).getByText("не велась")).toBeInTheDocument();
    expect(within(first).getByText(/нужна работа: нет записей за 14 дн\./)).toBeInTheDocument();
    expect(first).toHaveClass("risk-row");

    const second = screen.getByRole("link", { name: "Андреева Елена" }).closest("tr") as HTMLElement;
    expect(within(second).getByText("2 зап., последняя 01.10.2026")).toBeInTheDocument();
    expect(within(second).getByText(/30\.09\.2026 \(просрочено\)/)).toBeInTheDocument();
    expect(within(second).getByText("работа ведётся")).toBeInTheDocument();
    expect(second).not.toHaveClass("risk-row");

    const third = screen.getByRole("link", { name: "Борисов Иван" }).closest("tr") as HTMLElement;
    expect(within(third).getByText("20.10.2026")).toBeInTheDocument();
    expect(within(third).queryByText(/просрочено/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Алексеев Пётр" })).toHaveAttribute("href", "/students/1");
  });

  it("смена группы запрашивает её журнал", async () => {
    const user = userEvent.setup();
    mock({ 7: group(7, "СА172", [row(1, "Алексеев Пётр", { work_count: 1, last_work_on: "2026-10-01" })]), 8: group(8, "ИИ212", [row(9, "Захаров Олег", { work_count: 1, last_work_on: "2026-10-02" })]) });
    renderPage(<IndividualWorkPage />, { role: "dept_head" });
    await screen.findByRole("link", { name: "Алексеев Пётр" });
    await user.selectOptions(screen.getByLabelText("Группа"), "8");
    expect(await screen.findByRole("link", { name: "Захаров Олег" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Алексеев Пётр" })).not.toBeInTheDocument();
  });

  it("в группе пусто — подсказка; нет доступных групп — сообщение", async () => {
    mock({ 7: group(7, "СА172", []) });
    const { unmount } = renderPage(<IndividualWorkPage />, { role: "curator" });
    expect(await screen.findByText(/В группе СА172 нет студентов с серией пропусков/)).toBeInTheDocument();
    unmount();
    mock({}, []);
    renderPage(<IndividualWorkPage />, { role: "curator" });
    expect(await screen.findByText("Нет доступных групп.")).toBeInTheDocument();
  });

  it("ошибки: список групп и журнал группы", async () => {
    get.mockRejectedValueOnce(new ApiError(500, "Сбой"));
    const { unmount } = renderPage(<IndividualWorkPage />, { role: "curator" });
    expect(await screen.findByText("Сбой")).toBeInTheDocument();
    unmount();
    get.mockImplementation(async (path: string) => {
      if (path === "/individual-work/groups") return GROUPS;
      throw new ApiError(403, "Нет доступа к этой группе");
    });
    renderPage(<IndividualWorkPage />, { role: "curator" });
    expect(await screen.findByText("Нет доступа к этой группе")).toBeInTheDocument();
  });
});
