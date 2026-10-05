import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { RosterEntry, RosterResponse } from "../api/types";
import { renderPage } from "../test/utils";
import { todayIso } from "../utils/date";
import CuratorCabinetPage from "./CuratorCabinetPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);

const MARK_CODES = [
  { id: 1, code: "н", name: "Неуважительная причина", counts_as_present: false, is_excused: false, requires_document: false, is_active: true },
  { id: 2, code: "б", name: "Больничный лист", counts_as_present: false, is_excused: true, requires_document: true, is_active: true },
];

function entry(id: number, name: string, over: Partial<RosterEntry> = {}): RosterEntry {
  return {
    student_id: id, full_name: name, mark_code: null, mark_name: null, comment: null, basis_reference: null,
    is_draft_suggestion: false, is_locked: false, risk_streak: 0, last_edited_by: null, last_edited_at: null, ...over,
  };
}

function roster(entries: RosterEntry[], over: Partial<RosterResponse> = {}): RosterResponse {
  return { study_group_id: 7, date: todayIso(), is_submitted: false, submitted_at: null, is_on_time: null, first_period: null, entries, ...over };
}

const RHYTHM = [
  { date: "2026-09-30", kind: "ok", absent: 0 },
  { date: "2026-10-01", kind: "absent", absent: 3 },
  { date: "2026-10-02", kind: "missing", absent: 0 },
];

function mockApi(r: RosterResponse, dayType = "study_day") {
  get.mockImplementation(async (path: string) => {
    if (path === "/curator/groups") return [{ id: 7, code: "СА172", course: 1, is_submitted_today: false }];
    if (path === "/curator/mark-codes") return MARK_CODES;
    if (path === "/curator/settings") return { risk_threshold_consecutive_unexcused: 3 };
    if (path.includes("/month-status")) return [{ date: todayIso(), day_type: dayType, is_submitted: false, is_on_time: null }];
    if (path.includes("/day?")) return r;
    if (path.endsWith("/rhythm")) return RHYTHM;
    throw new Error(`неожиданный запрос ${path}`);
  });
}

const studentRow = (name: string) => screen.getByRole("row", { name: new RegExp(name) });

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});

describe("CuratorCabinetPage — журнал дня", () => {
  it("показывает студентов группы и статус дня", async () => {
    mockApi(roster([entry(1, "Алексеев Пётр"), entry(2, "Андреева Елена")]));
    renderPage(<CuratorCabinetPage />, { role: "curator" });
    expect(await screen.findByText("День ещё не сдан — можно заполнить")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Алексеев Пётр" })).toHaveAttribute("href", "/students/1");
    expect(screen.getByText("Отсутствуют: 0")).toBeInTheDocument();
  });

  it("нет закреплённых групп — подсказка", async () => {
    get.mockImplementation(async (path: string) => (path === "/curator/groups" ? [] : []));
    renderPage(<CuratorCabinetPage />, { role: "curator" });
    expect(await screen.findByText("У вас нет закреплённых групп.")).toBeInTheDocument();
  });

  it("нерабочий день: вместо списка пояснение, отметок нет", async () => {
    mockApi(roster([entry(1, "Алексеев Пётр")]), "weekend");
    renderPage(<CuratorCabinetPage />, { role: "curator" });
    expect(await screen.findByText(/Нерабочий день/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Сдать день" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Алексеев Пётр" })).not.toBeInTheDocument();
  });

  it("подсвечивает риск (серия неуважительных) по порогу из настроек", async () => {
    mockApi(roster([entry(1, "Алексеев Пётр", { risk_streak: 3 }), entry(2, "Андреева Елена", { risk_streak: 2 })]));
    renderPage(<CuratorCabinetPage />, { role: "curator" });
    await screen.findByText("Алексеев Пётр");
    expect(within(studentRow("Алексеев")).getByText(/риск: 3 дн\. подряд/)).toBeInTheDocument();
    expect(within(studentRow("Андреева")).queryByText(/риск/)).not.toBeInTheDocument();
  });

  it("отметка студента увеличивает счётчик отсутствующих и уходит в «Сдать день»", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр"), entry(2, "Андреева Елена")]));
    renderPage(<CuratorCabinetPage />, { role: "curator" });
    await screen.findByText("Алексеев Пётр");
    await user.click(within(studentRow("Алексеев")).getByRole("button", { name: "Н" }));
    expect(screen.getByText("Отсутствуют: 1")).toBeInTheDocument();

    post.mockResolvedValue(roster([entry(1, "Алексеев Пётр", { mark_code: "н" })], { is_submitted: true }));
    await user.click(screen.getByRole("button", { name: "Сдать день" }));
    expect(post).toHaveBeenCalledWith(`/curator/groups/7/day/submit?date=${todayIso()}`, {
      exceptions: [{ student_id: 1, mark_code: "н", comment: null, basis_reference: null }],
      first_period: null,
    });
    expect(await screen.findByText("День сдан")).toBeInTheDocument();
  });

  it("снятая отметка («Я») убирает студента из отсутствующих", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    renderPage(<CuratorCabinetPage />, { role: "curator" });
    await screen.findByText("Алексеев Пётр");
    const row = studentRow("Алексеев");
    await user.click(within(row).getByRole("button", { name: "Б" }));
    expect(screen.getByText("Отсутствуют: 1")).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Я" }));
    expect(screen.getByText("Отсутствуют: 0")).toBeInTheDocument();
  });

  it("уже стоящие отметки подгружаются как отсутствующие, а заблокированные периодом — нет", async () => {
    mockApi(roster([
      entry(1, "Алексеев Пётр", { mark_code: "н", mark_name: "Неуважительная причина" }),
      entry(2, "Андреева Елена", { mark_code: "б", mark_name: "Больничный лист", is_locked: true }),
    ]));
    renderPage(<CuratorCabinetPage />, { role: "curator" });
    await screen.findByText("Алексеев Пётр");
    expect(screen.getByText("Отсутствуют: 1")).toBeInTheDocument();
    expect(within(studentRow("Андреева")).getByText("Больничный лист")).toBeInTheDocument();
  });
});

describe("CuratorCabinetPage — «Все присутствуют» (защита от потери отметок)", () => {
  async function withOneAbsence() {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    renderPage(<CuratorCabinetPage />, { role: "curator" });
    await screen.findByText("Алексеев Пётр");
    await user.click(within(studentRow("Алексеев")).getByRole("button", { name: "Н" }));
    return user;
  }

  it("при несохранённых отметках спрашивает подтверждение; отказ ничего не отправляет", async () => {
    const user = await withOneAbsence();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await user.click(screen.getByRole("button", { name: "Все присутствуют" }));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("(1)"));
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByText("Отсутствуют: 1")).toBeInTheDocument(); // отметка на месте
  });

  it("после согласия отправляет «все присутствуют»", async () => {
    const user = await withOneAbsence();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    post.mockResolvedValue(roster([entry(1, "Алексеев Пётр")], { is_submitted: true }));
    await user.click(screen.getByRole("button", { name: "Все присутствуют" }));
    expect(post).toHaveBeenCalledWith(`/curator/groups/7/day/mark-all-present?date=${todayIso()}`, undefined);
    expect(await screen.findByText("День сдан")).toBeInTheDocument();
  });

  it("без отметок — сразу, без вопроса", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    renderPage(<CuratorCabinetPage />, { role: "curator" });
    await screen.findByText("Алексеев Пётр");
    const confirm = vi.spyOn(window, "confirm");
    post.mockResolvedValue(roster([entry(1, "Алексеев Пётр")], { is_submitted: true }));
    await user.click(screen.getByRole("button", { name: "Все присутствуют" }));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(confirm).not.toHaveBeenCalled();
  });

  it("сервер просит подтвердить стирание уже сданных отметок (409) — повтор с confirm=true только после согласия", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр", { mark_code: "н", mark_name: "Неуважительная причина", is_locked: true })]));
    renderPage(<CuratorCabinetPage />, { role: "curator" });
    await screen.findByText("Алексеев Пётр");
    post.mockRejectedValueOnce(new ApiError(409, "На этот день уже внесено отметок: 1."));
    post.mockResolvedValueOnce(roster([entry(1, "Алексеев Пётр")], { is_submitted: true }));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    await user.click(screen.getByRole("button", { name: "Все присутствуют" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("уже внесено отметок"));
    expect(post.mock.calls[1][0]).toContain("&confirm=true");
  });

  it("отказ на 409 оставляет всё как было", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    renderPage(<CuratorCabinetPage />, { role: "curator" });
    await screen.findByText("Алексеев Пётр");
    post.mockRejectedValueOnce(new ApiError(409, "На этот день уже внесено отметок: 1."));
    vi.spyOn(window, "confirm").mockReturnValue(false);
    await user.click(screen.getByRole("button", { name: "Все присутствуют" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).not.toContain("confirm=true");
  });

  it("ошибка сдачи показывается", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    renderPage(<CuratorCabinetPage />, { role: "curator" });
    await screen.findByText("Алексеев Пётр");
    post.mockRejectedValue(new ApiError(400, "Неизвестный код отметки"));
    await user.click(screen.getByRole("button", { name: "Сдать день" }));
    expect(await screen.findByText("Неизвестный код отметки")).toBeInTheDocument();
  });

  it("ритм группы за три недели — под шапкой журнала", async () => {
    mockApi(roster([]));
    renderPage(<CuratorCabinetPage />, { role: "curator" });
    const rhythm = await screen.findByRole("img", { name: /Ритм за 3 дня: учебных 3, с пропусками без причины 1, не сдано 1/ });
    expect(rhythm.querySelector('[title="01.10: пропуски без причины — 3"]')).not.toBeNull();
    expect(get).toHaveBeenCalledWith("/curator/groups/7/rhythm");
  });
});
