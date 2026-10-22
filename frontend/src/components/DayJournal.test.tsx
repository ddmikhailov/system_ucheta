import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, RouterProvider, createMemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { RosterEntry, RosterResponse } from "../api/types";
import { AuthContext } from "../auth/authContextObject";
import { makeUser } from "../test/utils";
import { todayIso } from "../utils/date";
import { dialogs } from "../utils/feedback";
import { journalDraftKey, readJournalDraft, saveJournalDraft } from "../utils/journalDraft";
import DayJournal from "./DayJournal";
import FeedbackHost from "./FeedbackHost";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);

const MARK_CODES = [
  { id: 1, code: "н", name: "Неуважительная причина", counts_as_present: false, is_excused: false, requires_document: false, is_active: true },
];
const KEY = () => journalDraftKey(1, 7, todayIso());

function entry(id: number, name: string, over: Partial<RosterEntry> = {}): RosterEntry {
  return {
    student_id: id, full_name: name, mark_code: null, mark_name: null, comment: null, basis_reference: null,
    is_draft_suggestion: false, is_locked: false, risk_streak: 0, attendance_percent: 100, is_risk: false, last_edited_by: null, last_edited_at: null, ...over,
  };
}

function roster(entries: RosterEntry[], over: Partial<RosterResponse> = {}): RosterResponse {
  return { study_group_id: 7, date: todayIso(), is_submitted: false, submitted_at: null, is_on_time: null, first_period: null, entries, ...over };
}

function mockApi(r: RosterResponse) {
  get.mockImplementation(async (path: string) => {
    if (path === "/curator/mark-codes") return MARK_CODES;
    if (path === "/curator/settings") return { risk_attendance_percent: 85 };
    if (path.includes("/month-status")) return [{ date: todayIso(), day_type: "study_day", is_submitted: false, is_on_time: null }];
    if (path.includes("/rhythm")) return [];
    if (path.includes("/day?")) return r;
    throw new Error(`неожиданный запрос ${path}`);
  });
}

/** Журнал одной группы на странице «/journal» и соседняя страница «/other» — для проверки ухода по меню. */
function renderJournal() {
  const router = createMemoryRouter(
    [
      {
        path: "/journal",
        element: (
          <>
            <Link to="/other">в другой раздел</Link>
            <DayJournal
              fetchGroups={async () => [{ id: 7, label: "СА172" }]}
              fixedGroupId={7}
              showGroupTools={false}
              emptyText="нет групп"
              notSubmittedText="День не сдан"
              submitLabel="Сдать день"
              submitErrorText="Не удалось сдать день"
            />
          </>
        ),
      },
      { path: "/other", element: <p>другой раздел</p> },
    ],
    { initialEntries: ["/journal"] }
  );
  const value = { user: makeUser("curator"), loading: false, login: vi.fn(), logout: vi.fn(), logoutAll: vi.fn(), refresh: vi.fn() };
  return render(
    <AuthContext.Provider value={value}>
      <RouterProvider router={router} />
      <FeedbackHost />
    </AuthContext.Provider>
  );
}

const studentRow = (name: string) => screen.getByRole("row", { name: new RegExp(name) });
const absentButton = (name: string) => within(studentRow(name)).getByRole("button", { name: "Н" });

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});

describe("DayJournal — несданные отметки не теряются", () => {
  it("отметка сразу ложится в черновик вкладки и восстанавливается при новом открытии журнала", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр"), entry(2, "Борисова Анна")]));
    const first = renderJournal();
    await screen.findByText("Алексеев Пётр");
    await user.click(absentButton("Алексеев"));
    expect(readJournalDraft(KEY())?.pending).toEqual({ 1: { mark_code: "н", comment: "", basis_reference: "" } });

    // Сессия истекла / вкладку перезагрузили: страница открывается заново.
    first.unmount();
    renderJournal();
    await screen.findByText("Алексеев Пётр");
    await waitFor(() => expect(absentButton("Алексеев")).toHaveAttribute("aria-pressed", "true"));
    expect(absentButton("Борисова")).toHaveAttribute("aria-pressed", "false");
    expect(await screen.findByText("Восстановлены несданные отметки этого дня")).toBeInTheDocument();
  });

  it("черновик не восстанавливается, если день на сервере с тех пор изменился", async () => {
    saveJournalDraft(KEY(), {
      pending: { 1: { mark_code: "н", comment: "", basis_reference: "" } },
      firstPeriod: "",
      baseline: "{}",
      submitted: false,
    });
    // Пока страницы не было, день сдал кто-то другой.
    mockApi(roster([entry(1, "Алексеев Пётр"), entry(2, "Борисова Анна", { mark_code: "н" })], { is_submitted: true }));
    renderJournal();
    expect(await screen.findByRole("button", { name: "Редактировать" })).toBeInTheDocument();
    expect(readJournalDraft(KEY())).toBeNull();
  });

  it("сдача дня стирает черновик", async () => {
    const user = userEvent.setup();
    const r = roster([entry(1, "Алексеев Пётр")]);
    mockApi(r);
    renderJournal();
    await screen.findByText("Алексеев Пётр");
    await user.click(absentButton("Алексеев"));
    expect(readJournalDraft(KEY())).not.toBeNull();

    post.mockResolvedValue({ ...r, is_submitted: true, entries: [entry(1, "Алексеев Пётр", { mark_code: "н" })] });
    await user.click(screen.getByRole("button", { name: "Сдать день" }));
    await waitFor(() => expect(readJournalDraft(KEY())).toBeNull());
  });

  it("уход по меню с несданными отметками спрашивает подтверждение", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    renderJournal();
    await screen.findByText("Алексеев Пётр");
    await user.click(absentButton("Алексеев"));

    const confirm = vi.spyOn(dialogs, "confirm").mockResolvedValue(false);
    await user.click(screen.getByRole("link", { name: "в другой раздел" }));
    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
    expect(confirm.mock.calls[0][0]).toMatch(/ещё не сданы/);
    expect(screen.getByText("Алексеев Пётр")).toBeInTheDocument();

    confirm.mockResolvedValue(true);
    await user.click(screen.getByRole("link", { name: "в другой раздел" }));
    expect(await screen.findByText("другой раздел")).toBeInTheDocument();
    // Ушли, не сдав: черновик ждёт возвращения.
    expect(readJournalDraft(KEY())).not.toBeNull();
  });

  it("без несданных отметок уходит без вопросов", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    renderJournal();
    await screen.findByText("Алексеев Пётр");
    const confirm = vi.spyOn(dialogs, "confirm");
    await user.click(screen.getByRole("link", { name: "в другой раздел" }));
    expect(await screen.findByText("другой раздел")).toBeInTheDocument();
    expect(confirm).not.toHaveBeenCalled();
  });

  it("закрытие вкладки с несданными отметками — браузер переспросит", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    renderJournal();
    await screen.findByText("Алексеев Пётр");
    const before = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(before);
    expect(before.defaultPrevented).toBe(false);

    await user.click(absentButton("Алексеев"));
    const after = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(after);
    expect(after.defaultPrevented).toBe(true);
  });
});
