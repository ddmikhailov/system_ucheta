import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../../api/client";
import type { RosterEntry, RosterResponse } from "../../api/types";
import { renderPage } from "../../test/utils";
import { todayIso } from "../../utils/date";
import GroupJournalTab from "./GroupJournalTab";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);

const MARK_CODES = [
  { id: 1, code: "н", name: "Неуважительная причина", counts_as_present: false, is_excused: false, requires_document: false, is_active: true },
  { id: 2, code: "б", name: "Больничный лист", counts_as_present: false, is_excused: true, requires_document: true, is_active: true },
];

const GROUPS = [
  { id: 7, code: "СА172", course: 1, is_active: true, curator_name: "Иванова Анна" },
  { id: 8, code: "ИИ212", course: 2, is_active: true, curator_name: null },
  { id: 9, code: "АРХИВ1", course: 4, is_active: false, curator_name: "Петров П." },
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

function mockApi(r: RosterResponse) {
  get.mockImplementation(async (path: string) => {
    if (path === "/admin/groups") return GROUPS;
    if (path === "/curator/mark-codes") return MARK_CODES;
    if (path === "/curator/settings") return { risk_threshold_consecutive_unexcused: 3 };
    if (path.includes("/month-status")) return [{ date: todayIso(), day_type: "study_day", is_submitted: false, is_on_time: null }];
    if (path.includes("/day?")) return r;
    throw new Error(`неожиданный запрос ${path}`);
  });
}

const groupSelect = () => screen.getAllByRole("combobox")[0];
const studentRow = (name: string) => screen.getByRole("row", { name: new RegExp(name) });

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});

describe("GroupJournalTab — журнал администрации", () => {
  it("группы берутся из /admin/groups: активные, с куратором или пометкой «нет куратора»", async () => {
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    renderPage(<GroupJournalTab />, { role: "admin" });
    await screen.findByText("Алексеев Пётр");
    const options = within(groupSelect()).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["СА172 (курс 1) — Иванова Анна", "ИИ212 (курс 2) — нет куратора"]);
    // первая группа открыта сразу
    expect(get).toHaveBeenCalledWith(`/curator/groups/7/day?date=${todayIso()}`);
  });

  it("нет групп в зоне видимости — подсказка", async () => {
    get.mockImplementation(async () => []);
    renderPage(<GroupJournalTab />, { role: "dept_head" });
    expect(await screen.findByText("Нет ни одной группы в зоне видимости.")).toBeInTheDocument();
  });

  it("не удалось загрузить группы — сообщение сервера", async () => {
    get.mockImplementation(async (path: string) => {
      if (path === "/admin/groups") throw new ApiError(403, "Нет доступа");
      return [];
    });
    renderPage(<GroupJournalTab />, { role: "dept_head" });
    expect(await screen.findByText("Нет доступа")).toBeInTheDocument();
  });

  it("тексты администрации: день можно заполнить самостоятельно, кнопка «Сохранить день»", async () => {
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    renderPage(<GroupJournalTab />, { role: "admin" });
    expect(await screen.findByText("День не активирован куратором — можно заполнить самостоятельно")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Сохранить день" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Сдать день" })).not.toBeInTheDocument();
  });

  it("смена группы запрашивает день другой группы; несохранённые отметки требуют подтверждения", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    renderPage(<GroupJournalTab />, { role: "admin" });
    await screen.findByText("Алексеев Пётр");
    await user.click(within(studentRow("Алексеев")).getByRole("button", { name: "Н" }));

    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await user.selectOptions(groupSelect(), "8");
    expect(confirm).toHaveBeenCalledWith("Несохранённые изменения будут потеряны. Сменить группу?");
    expect(get).not.toHaveBeenCalledWith(`/curator/groups/8/day?date=${todayIso()}`);

    confirm.mockReturnValue(true);
    await user.selectOptions(groupSelect(), "8");
    expect(get).toHaveBeenCalledWith(`/curator/groups/8/day?date=${todayIso()}`);
    confirm.mockRestore();
  });

  it("сохранение дня уходит в тот же эндпоинт, ошибка сервера показывается", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    renderPage(<GroupJournalTab />, { role: "admin" });
    await screen.findByText("Алексеев Пётр");
    await user.click(within(studentRow("Алексеев")).getByRole("button", { name: "Н" }));

    post.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await user.click(screen.getByRole("button", { name: "Сохранить день" }));
    expect(await screen.findByText("Не удалось сохранить день")).toBeInTheDocument();

    post.mockResolvedValueOnce(roster([entry(1, "Алексеев Пётр", { mark_code: "н" })], { is_submitted: true, is_on_time: false }));
    await user.click(screen.getByRole("button", { name: "Сохранить день" }));
    expect(post).toHaveBeenLastCalledWith(`/curator/groups/7/day/submit?date=${todayIso()}`, {
      exceptions: [{ student_id: 1, mark_code: "н", comment: null, basis_reference: null }],
      first_period: null,
    });
    expect(await screen.findByText("День сдан (задним числом)")).toBeInTheDocument();
  });
});

describe("GroupJournalTab — комментарий к отметке", () => {
  it("видно, кто и когда правил отметку", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр", { mark_code: "н", last_edited_by: "Сидорова М.", last_edited_at: "2026-10-01T09:30:00" })]));
    renderPage(<GroupJournalTab />, { role: "admin" });
    await screen.findByText("Алексеев Пётр");
    await user.click(screen.getByRole("button", { name: "Добавить комментарий" }));
    expect(await screen.findByText(/Сидорова М\./)).toBeInTheDocument();
  });

  it("введённый комментарий попадает в отправку и меняет подпись кнопки", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр", { mark_code: "б" })]));
    renderPage(<GroupJournalTab />, { role: "admin" });
    await screen.findByText("Алексеев Пётр");
    await user.click(screen.getByRole("button", { name: "Добавить комментарий" }));
    const dialog = await screen.findByRole("dialog");
    const inputs = within(dialog).getAllByRole("textbox");
    await user.type(inputs[0], "болеет");
    await user.type(inputs[1], "справка №5");
    await user.click(within(dialog).getByRole("button", { name: /Сохранить|Готово|ОК/ }));
    expect(await screen.findByRole("button", { name: "Комментарий добавлен" })).toBeInTheDocument();

    post.mockResolvedValue(roster([entry(1, "Алексеев Пётр", { mark_code: "б" })], { is_submitted: true }));
    await user.click(screen.getByRole("button", { name: "Сохранить день" }));
    expect(post).toHaveBeenCalledWith(expect.stringContaining("/day/submit"), {
      exceptions: [{ student_id: 1, mark_code: "б", comment: "болеет", basis_reference: "справка №5" }],
      first_period: null,
    });
  });
});

describe("GroupJournalTab — окно «Период» (длительное отсутствие)", () => {
  async function openPeriod() {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    renderPage(<GroupJournalTab />, { role: "admin" });
    await screen.findByText("Алексеев Пётр");
    await user.click(within(studentRow("Алексеев")).getByRole("button", { name: "Период" }));
    const dialog = await screen.findByRole("dialog", { name: "Длительное отсутствие" });
    return { user, dialog };
  }

  it("предлагает только уважительные коды и сохраняет период, после чего перечитывает день", async () => {
    const { user, dialog } = await openPeriod();
    expect(within(dialog).getByText(/Алексеев Пётр/)).toBeInTheDocument();
    const options = within(within(dialog).getByRole("combobox")).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Больничный лист"]);

    post.mockResolvedValue({});
    const dayCalls = () => get.mock.calls.filter(([p]) => String(p).includes("/day?")).length;
    const before = dayCalls();
    await user.type(within(dialog).getByPlaceholderText(/приказа/), "приказ 12");
    await user.click(within(dialog).getByRole("button", { name: "Сохранить" }));
    expect(post).toHaveBeenCalledWith("/curator/absence-periods", {
      student_id: 1, mark_code: "б", date_from: todayIso(), date_to: todayIso(), basis_reference: "приказ 12",
    });
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(dayCalls()).toBeGreaterThan(before);
  });

  it("дата окончания раньше начала — сообщение, на сервер не уходит", async () => {
    const { dialog } = await openPeriod();
    const [from, to] = Array.from(dialog.querySelectorAll<HTMLInputElement>("input[type=date]"));
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(from, { target: { value: todayIso() } });
    fireEvent.change(to, { target: { value: "2020-01-01" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));
    expect(await within(dialog).findByText("Дата окончания раньше даты начала")).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("ошибка сервера остаётся в окне, «Отмена» закрывает без запроса", async () => {
    const { user, dialog } = await openPeriod();
    post.mockRejectedValueOnce(new ApiError(409, "Период пересекается с другим"));
    await user.click(within(dialog).getByRole("button", { name: "Сохранить" }));
    expect(await within(dialog).findByText("Период пересекается с другим")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Отмена" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(1);
  });
});
