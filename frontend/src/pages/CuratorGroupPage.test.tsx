import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { RosterEntry, RosterResponse } from "../api/types";
import { renderPage } from "../test/utils";
import { todayIso } from "../utils/date";
import CuratorGroupPage from "./CuratorGroupPage";

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
    is_draft_suggestion: false, is_locked: false, risk_streak: 0, attendance_percent: 100, is_risk: false, last_edited_by: null, last_edited_at: null, ...over,
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
    if (path === "/curator/groups") return [GROUP];
    if (path === "/curator/mark-codes") return MARK_CODES;
    if (path === "/curator/settings") return { risk_threshold_consecutive_unexcused: 3 };
    if (path.includes("/month-status")) return [{ date: todayIso(), day_type: dayType, is_submitted: false, is_on_time: null }];
    if (path.includes("/day?")) return r;
    if (path.endsWith("/rhythm")) return RHYTHM;
    throw new Error(`неожиданный запрос ${path}`);
  });
}

const GROUP = { id: 7, code: "СА172", course: 1, is_submitted_today: false, students_count: 2, risk_count: 0, role_type: "curator" };

const studentRow = (name: string) => screen.getByRole("row", { name: new RegExp(name) });

// Журнал куратора — вкладка «Журнал» на странице группы (интерфейс 3.2).
function open(tab?: string) {
  return renderPage(<CuratorGroupPage />, {
    role: "curator",
    route: `/cabinet/groups/7${tab ? `?tab=${tab}` : ""}`,
    path: "/cabinet/groups/:groupId",
  });
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});

describe("CuratorGroupPage — журнал дня", () => {
  it("показывает студентов группы и статус дня", async () => {
    mockApi(roster([entry(1, "Алексеев Пётр"), entry(2, "Андреева Елена")]));
    open();
    expect(await screen.findByText("День ещё не сдан — можно заполнить")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Алексеев Пётр" })).toHaveAttribute("href", "/students/1");
    expect(screen.getByText("Отсутствуют: 0")).toBeInTheDocument();
  });

  it("«Список для печати» открывает окно выбора столбцов для текущей группы", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    open("students");
    await screen.findByRole("link", { name: "Алексеев Пётр" });

    await user.click(screen.getByRole("button", { name: "Список для печати" }));

    const dialog = await screen.findByRole("dialog", { name: "Список группы для печати" });
    expect(within(dialog).getByRole("heading", { name: /Список группы СА172 для печати/ })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Скачать .docx" })).toBeEnabled();
  });

  it("«Личные карточки» открывают окно выбора полей для карточек всей группы", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    open("students");
    await screen.findByRole("link", { name: "Алексеев Пётр" });

    await user.click(screen.getByRole("button", { name: "Личные карточки" }));

    const dialog = await screen.findByRole("dialog", { name: "Личная карточка в Word" });
    expect(within(dialog).getByRole("heading", { name: "Личные карточки группы СА172" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Скачать .docx" })).toBeEnabled();
  });

  it("нерабочий день: вместо списка пояснение, отметок нет", async () => {
    mockApi(roster([entry(1, "Алексеев Пётр")]), "weekend");
    open();
    expect(await screen.findByText(/Нерабочий день/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Сдать день" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Алексеев Пётр" })).not.toBeInTheDocument();
  });

  it("подсвечивает группу риска: посещаемость с начала семестра ниже порога, процент в подписи", async () => {
    mockApi(roster([entry(1, "Алексеев Пётр", { attendance_percent: 78.5, is_risk: true }), entry(2, "Андреева Елена", { attendance_percent: 91 })]));
    open();
    await screen.findByText("Алексеев Пётр");
    expect(within(studentRow("Алексеев")).getByText(/риск: посещаемость 78,5 %/)).toBeInTheDocument();
    expect(within(studentRow("Андреева")).queryByText(/риск/)).not.toBeInTheDocument();
  });

  it("отметка студента увеличивает счётчик отсутствующих и уходит в «Сдать день»", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр"), entry(2, "Андреева Елена")]));
    open();
    await screen.findByText("Алексеев Пётр");
    await user.click(within(studentRow("Алексеев")).getByRole("button", { name: "Н" }));
    expect(screen.getByText("Отсутствуют: 1")).toBeInTheDocument();

    post.mockResolvedValue(roster([entry(1, "Алексеев Пётр", { mark_code: "н" })], { is_submitted: true }));
    await user.click(screen.getByRole("button", { name: "Сдать день" }));
    expect(post).toHaveBeenCalledWith(`/curator/groups/7/day/submit?date=${todayIso()}`, {
      exceptions: [{ student_id: 1, mark_code: "н", comment: null, basis_reference: null }],
      first_period: null,
    });
    expect(await screen.findByRole("region", { name: "Итоги дня" })).toBeInTheDocument();
  });

  it("снятая отметка («Я») убирает студента из отсутствующих", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    open();
    await screen.findByText("Алексеев Пётр");
    const row = studentRow("Алексеев");
    await user.click(within(row).getByRole("button", { name: "Б" }));
    expect(screen.getByText("Отсутствуют: 1")).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Присутствует" }));
    expect(screen.getByText("Отсутствуют: 0")).toBeInTheDocument();
  });

  it("уже стоящие отметки подгружаются как отсутствующие, а заблокированные периодом — нет", async () => {
    mockApi(roster([
      entry(1, "Алексеев Пётр", { mark_code: "н", mark_name: "Неуважительная причина" }),
      entry(2, "Андреева Елена", { mark_code: "б", mark_name: "Больничный лист", is_locked: true }),
    ]));
    open();
    await screen.findByText("Алексеев Пётр");
    expect(screen.getByText("Отсутствуют: 1")).toBeInTheDocument();
    expect(within(studentRow("Андреева")).getByText("Больничный лист")).toBeInTheDocument();
  });
});

describe("CuratorGroupPage — «Все присутствуют» (защита от потери отметок)", () => {
  async function withOneAbsence() {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    open();
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
    expect(await screen.findByRole("region", { name: "Итоги дня" })).toBeInTheDocument();
  });

  it("без отметок — сразу, без вопроса", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    open();
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
    open();
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
    open();
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
    open();
    await screen.findByText("Алексеев Пётр");
    post.mockRejectedValue(new ApiError(400, "Неизвестный код отметки"));
    await user.click(screen.getByRole("button", { name: "Сдать день" }));
    expect(await screen.findByText("Неизвестный код отметки")).toBeInTheDocument();
  });

  it("ритм группы за три недели — под шапкой журнала", async () => {
    mockApi(roster([]));
    open();
    const rhythm = await screen.findByRole("img", { name: /Ритм за 3 дня: учебных 3, с пропусками без причины 1, не сдано 1/ });
    expect(rhythm.querySelector('[title="01.10: пропуски без причины — 3"]')).not.toBeNull();
    expect(get).toHaveBeenCalledWith("/curator/groups/7/rhythm");
  });
});


describe("CuratorGroupPage — сданный день и правка прошлого дня", () => {
  it("сданный день — итоги вместо формы; «Редактировать» открывает форму, «Отменить» возвращает итоги", async () => {
    const user = userEvent.setup();
    mockApi(
      roster([entry(1, "Алексеев Пётр", { mark_code: "н", mark_name: "Неуважительная причина" }), entry(2, "Андреева Елена")], {
        is_submitted: true, submitted_at: "2026-10-05T06:30:00", is_on_time: true, submitted_by_name: "Иванова Анна",
      })
    );
    open();
    const summary = await screen.findByRole("region", { name: "Итоги дня" });
    expect(within(summary).getByText(/Иванова Анна · вовремя/)).toBeInTheDocument();
    expect(within(summary).getByText("1 из 2")).toBeInTheDocument();
    expect(within(summary).getByRole("link", { name: "Алексеев Пётр" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Сдать день" })).not.toBeInTheDocument();

    await user.click(within(summary).getByRole("button", { name: "Редактировать" }));
    expect(screen.getByText("Отсутствуют: 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Сохранить изменения" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Отменить" }));
    expect(screen.getByRole("region", { name: "Итоги дня" })).toBeInTheDocument();
  });

  it("прошлый сданный день: правка уходит запросом на проверку с причиной, а не в журнал", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр", { mark_code: "н" })], { is_submitted: true, is_on_time: true, edit_requires_review: true }));
    open();
    await user.click(await screen.findByRole("button", { name: "Предложить исправление" }));
    expect(screen.getByText(/уйдёт на проверку зав. отделением/)).toBeInTheDocument();
    await user.click(within(studentRow("Алексеев")).getByRole("button", { name: "Б" }));

    const prompt = vi.spyOn(window, "prompt").mockReturnValueOnce("Принесли справку");
    post.mockResolvedValue(
      roster([entry(1, "Алексеев Пётр", { mark_code: "н" })], {
        is_submitted: true, edit_requires_review: true,
        pending_change: {
          id: 5, study_group_id: 7, group_code: "СА172", date: todayIso(), requested_by_id: 1, requested_by_name: "Тестов Тест",
          created_at: "2026-10-05T07:00:00", reason: "Принесли справку", status: "pending", reviewed_by_name: null,
          reviewed_at: null, review_comment: null, first_period: null,
          changes: [{ student_id: 1, full_name: "Алексеев Пётр", from_code: "н", to_code: "б", details_changed: false }],
        },
      })
    );
    await user.click(screen.getByRole("button", { name: "Отправить на проверку" }));
    expect(prompt).toHaveBeenCalled();
    expect(post).toHaveBeenCalledWith(`/curator/groups/7/day/change-request?date=${todayIso()}`, {
      exceptions: [{ student_id: 1, mark_code: "б", comment: null, basis_reference: null }],
      first_period: null,
      reason: "Принесли справку",
    });
    expect(await screen.findByText("На проверке")).toBeInTheDocument();
    expect(screen.getByText("Принесли справку")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Отозвать" })).toBeInTheDocument(); // автор может отозвать
  });

  it("без причины запрос не уходит", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")], { is_submitted: true, edit_requires_review: true }));
    open();
    await user.click(await screen.findByRole("button", { name: "Предложить исправление" }));
    vi.spyOn(window, "prompt").mockReturnValueOnce("  ");
    await user.click(screen.getByRole("button", { name: "Отправить на проверку" }));
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByText(/Напишите причину исправления/)).toBeInTheDocument();
  });

  it("стрелки и «Сегодня» листают дни; будущих дней нет", async () => {
    const user = userEvent.setup();
    mockApi(roster([entry(1, "Алексеев Пётр")]));
    open();
    await screen.findByRole("link", { name: "Алексеев Пётр" });
    expect(screen.getByRole("button", { name: "Следующий учебный день" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Сегодня" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Предыдущий учебный день" }));
    await waitFor(() => expect(get).toHaveBeenCalledWith(expect.stringMatching(/\/curator\/groups\/7\/day\?date=/)));
    expect(screen.getByRole("button", { name: "Сегодня" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Следующий учебный день" })).toBeEnabled();
  });

  it("вкладки группы: студенты — весь список со ссылками на карточки", async () => {
    mockApi(roster([entry(1, "Алексеев Пётр", { attendance_percent: 78.5, is_risk: true }), entry(2, "Андреева Елена")]));
    open("students");
    expect(await screen.findByRole("link", { name: "Алексеев Пётр" })).toHaveAttribute("href", "/students/1");
    expect(within(studentRow("Алексеев")).getByText("группа риска")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Студенты/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tablist", { name: "Разделы группы" })).toHaveTextContent("Соц. паспорт");
  });

  it("чужая группа — понятное сообщение", async () => {
    get.mockImplementation(async (path: string) => (path === "/curator/groups" ? [] : []));
    open();
    expect(await screen.findByText("Эта группа не закреплена за вами")).toBeInTheDocument();
  });
});
