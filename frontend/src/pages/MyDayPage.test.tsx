import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { MyDay } from "../api/types";
import { renderPage } from "../test/utils";
import FeedbackHost from "../components/FeedbackHost";
import { resetFeedback } from "../utils/feedback";
import MyDayPage from "./MyDayPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);

function day(over: Partial<MyDay> = {}): MyDay {
  return {
    today: "2026-10-02", leads_groups: true, no_work_days: 14, attention_total: 0, attention: [], tasks: [],
    birthdays: [], review_waiting: null,
    groups: [{ id: 7, code: "СА172", course: 1, today_status: "submitted", is_on_time: true, missed_dates: [], missed_total: 0 }],
    ...over,
  };
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
  resetFeedback();
});

describe("MyDayPage", () => {
  it("показывает дату и сообщение «всё в порядке», когда срочного нет", async () => {
    get.mockResolvedValue(day());
    renderPage(<MyDayPage />, { role: "curator" });
    expect(await screen.findByText("Пятница, 2 октября")).toBeInTheDocument();
    expect(screen.getByText("На сегодня всё в порядке: срочного нет.")).toBeInTheDocument();
    expect(screen.getByText("день сдан")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/my-day");
  });

  it("группа с несданным днём и несданными днями прошлых недель — со ссылками на журнал нужной даты", async () => {
    get.mockResolvedValue(day({
      groups: [
        { id: 7, code: "СА172", course: 1, today_status: "pending", is_on_time: null, missed_dates: ["2026-10-01", "2026-09-30"], missed_total: 7 },
        { id: 8, code: "ИИ212", course: 2, today_status: "no_study_day", is_on_time: null, missed_dates: [], missed_total: 0 },
      ],
    }));
    renderPage(<MyDayPage />, { role: "curator" });
    expect(await screen.findByText("день не сдан")).toBeInTheDocument();
    expect(screen.getByText("сегодня занятий нет")).toBeInTheDocument();
    expect(screen.queryByText(/всё в порядке/)).not.toBeInTheDocument();
    expect(screen.getByText(/Не сданы 7 дней/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "01.10" })).toHaveAttribute("href", "/cabinet?group=7&date=2026-10-01");
    expect(screen.getByRole("link", { name: "30.09" })).toHaveAttribute("href", "/cabinet?group=7&date=2026-09-30");
    expect(screen.getByText(/и ранее/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "ИИ212" })).toHaveAttribute("href", "/cabinet?group=8");
  });

  it("если все пропущенные дни показаны, «и ранее» нет; один день — «1 день»", async () => {
    get.mockResolvedValue(day({
      groups: [{ id: 7, code: "СА172", course: 1, today_status: "submitted", is_on_time: true, missed_dates: ["2026-10-01"], missed_total: 1 }],
    }));
    renderPage(<MyDayPage />, { role: "curator" });
    expect(await screen.findByText(/Не сданы 1 день/)).toBeInTheDocument();
    expect(screen.queryByText(/и ранее/)).not.toBeInTheDocument();
  });

  it("задачи: просрочена, возвращена, скоро срок — с понятной подписью и ссылкой на назначение", async () => {
    get.mockResolvedValue(day({
      tasks: [
        { assignment_id: 11, title: "Кружки", group_code: "СА172", due_date: "2026-09-30", kind: "overdue", status: "in_progress", days_left: -2 },
        { assignment_id: 12, title: "Видеовизитка", group_code: "СА172", due_date: "2026-10-06", kind: "returned", status: "returned", days_left: 4 },
        { assignment_id: 13, title: "Отчёт", group_code: "СА172", due_date: "2026-10-02", kind: "due_soon", status: "new", days_left: 0 },
        { assignment_id: 14, title: "План", group_code: "СА172", due_date: "2026-10-04", kind: "due_soon", status: "new", days_left: 2 },
        { assignment_id: 15, title: "Вернули и просрочили", group_code: "СА172", due_date: "2026-10-01", kind: "overdue", status: "returned", days_left: -1 },
      ],
    }));
    renderPage(<MyDayPage />, { role: "curator" });
    expect(await screen.findByRole("link", { name: "Кружки" })).toHaveAttribute("href", "/tasks/assignment/11");
    expect(screen.getByText(/просрочено на 2 дня \(до 30\.09\.2026\)/)).toBeInTheDocument();
    expect(screen.getByText(/возвращено на доработку \(до 06\.10\.2026\)/)).toBeInTheDocument();
    expect(screen.getByText(/срок — сегодня/)).toBeInTheDocument();
    expect(screen.getByText(/осталось 2 дня/)).toBeInTheDocument();
    expect(screen.getByText(/просрочено на 1 день, возвращено на доработку/)).toBeInTheDocument();
  });

  it("внимание: причины по каждому студенту; «Записать» открывает форму и сохраняет заметку, список обновляется", async () => {
    const user = userEvent.setup();
    get.mockResolvedValueOnce(day({
      attention_total: 3,
      attention: [
        { student_id: 1, full_name: "Алексеев Пётр", group_code: "СА172", risk_streak: 5, attendance_percent: 62, needs_work: true, last_work_on: null, follow_up_on: null, follow_up_overdue: false, follow_up_today: false },
        { student_id: 2, full_name: "Андреева Елена", group_code: "СА172", risk_streak: 0, attendance_percent: 100, needs_work: false, last_work_on: "2026-09-20", follow_up_on: "2026-09-30", follow_up_overdue: true, follow_up_today: false },
        { student_id: 3, full_name: "Борисов Иван", group_code: "СА172", risk_streak: 0, attendance_percent: 100, needs_work: false, last_work_on: "2026-09-25", follow_up_on: "2026-10-02", follow_up_overdue: false, follow_up_today: true },
      ],
    }));
    get.mockResolvedValue(day());
    post.mockResolvedValue({});
    renderPage(
      <>
        <MyDayPage />
        <FeedbackHost />
      </>,
      { role: "curator" }
    );
    expect(await screen.findByText("посещаемость 62 %, записей за 14 дн. нет")).toBeInTheDocument();
    expect(screen.getByText("вернуться к вопросу было до 30.09.2026")).toBeInTheDocument();
    expect(screen.getByText("вернуться к вопросу сегодня")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Алексеев Пётр" })).toHaveAttribute("href", "/students/1");

    await user.click(screen.getByRole("button", { name: "Записать: Алексеев Пётр" }));
    const dialog = screen.getByRole("dialog", { name: "Запись индивидуальной работы" });
    expect(within(dialog).getByText("Запись: Алексеев Пётр")).toBeInTheDocument();
    const save = within(dialog).getByRole("button", { name: "Сохранить запись" });
    await user.click(save);
    expect(post).not.toHaveBeenCalled(); // без содержания сохранять нечего
    // Для звонка и беседы — поля протокола и «Сохранить и скачать протокол», как в карточке студента.
    expect(within(dialog).getByRole("heading", { name: "Для протокола беседы в Word" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Сохранить и скачать протокол" })).toBeInTheDocument();
    await user.selectOptions(within(dialog).getByLabelText("Вид записи"), "call");
    await user.type(within(dialog).getByPlaceholderText(/Что произошло/), "Позвонил матери");
    await user.click(save);

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const [url, body] = post.mock.calls[0] as [string, Record<string, unknown>];
    expect(url).toBe("/students/1/dossier/notes");
    expect(body).toMatchObject({ kind: "call", text: "Позвонил матери" });
    expect(body.occurred_on).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(body).not.toHaveProperty("follow_up_on");
    expect(await screen.findByText("Запись сохранена: Алексеев Пётр.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2); // сводка перечитана
    expect(screen.queryByText(/посещаемость \d/)).not.toBeInTheDocument();
  });

  it("форма записи из «Моего дня»: срок возврата уходит на сервер, ошибка показана, окно не закрывается, Отмена закрывает", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue(day({
      attention_total: 1,
      attention: [{ student_id: 1, full_name: "Алексеев Пётр", group_code: "СА172", risk_streak: 4, attendance_percent: 70, needs_work: true, last_work_on: null, follow_up_on: null, follow_up_overdue: false, follow_up_today: false }],
    }));
    post.mockRejectedValueOnce(new ApiError(400, "Вернуться к вопросу нужно не раньше даты события"));
    renderPage(<MyDayPage />, { role: "curator" });
    await user.click(await screen.findByRole("button", { name: "Записать: Алексеев Пётр" }));
    const dialog = screen.getByRole("dialog", { name: "Запись индивидуальной работы" });
    await user.type(within(dialog).getByPlaceholderText(/Что произошло/), "Беседа");
    const dateInput = within(dialog).getByLabelText(/Вернуться к вопросу/);
    await user.type(dateInput, "2099-01-15");
    await user.click(within(dialog).getByRole("button", { name: "Сохранить запись" }));
    expect(await within(dialog).findByText("Вернуться к вопросу нужно не раньше даты события")).toBeInTheDocument();
    expect(post.mock.calls[0][1]).toMatchObject({ follow_up_on: "2099-01-15" });
    expect(within(dialog).getByRole("button", { name: "Сохранить запись" })).toBeEnabled(); // можно исправить и повторить
    await user.click(within(dialog).getByRole("button", { name: "Отмена" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("список внимания обрезан — подсказка с полным числом", async () => {
    get.mockResolvedValue(day({
      attention_total: 41,
      attention: [{ student_id: 1, full_name: "Алексеев Пётр", group_code: "СА172", risk_streak: 4, attendance_percent: 70, needs_work: true, last_work_on: null, follow_up_on: null, follow_up_overdue: false, follow_up_today: false }],
    }));
    renderPage(<MyDayPage />, { role: "curator" });
    expect(await screen.findByText(/Показаны первые 1 из 41/)).toBeInTheDocument();
  });

  it("дни рождения: сегодня выделено, остальные — с датой и возрастом", async () => {
    get.mockResolvedValue(day({
      birthdays: [
        { student_id: 1, full_name: "Алексеев Пётр", group_code: "СА172", date: "2026-10-02", days_until: 0, turns: 18 },
        { student_id: 2, full_name: "Андреева Елена", group_code: "СА172", date: "2026-10-03", days_until: 1, turns: 17 },
        { student_id: 3, full_name: "Борисов Иван", group_code: "СА172", date: "2026-10-07", days_until: 5, turns: 16 },
      ],
    }));
    renderPage(<MyDayPage />, { role: "curator" });
    expect(await screen.findByText("сегодня")).toBeInTheDocument();
    expect(screen.getByText(/исполняется 18/)).toBeInTheDocument();
    expect(screen.getByText(/03\.10 \(через 1 день\)/)).toBeInTheDocument();
    expect(screen.getByText(/07\.10 \(через 5 дней\)/)).toBeInTheDocument();
  });

  it("проверяющему без групп — счётчик «На проверке» со ссылкой на задачи, без блоков групп", async () => {
    get.mockResolvedValue(day({ leads_groups: false, groups: [], review_waiting: { count: 3, oldest_submitted_at: "2026-09-30T10:00:00" } }));
    renderPage(<MyDayPage />, { role: "dept_head" });
    expect(await screen.findByRole("link", { name: "Ждут вашего решения: 3" })).toHaveAttribute("href", "/tasks");
    expect(screen.queryByText("Посещаемость")).not.toBeInTheDocument();
    expect(screen.queryByText("У вас нет закреплённых групп.")).not.toBeInTheDocument();
  });

  it("нет ни групп, ни проверок — сообщение; нулевой счётчик проверки не показывается", async () => {
    get.mockResolvedValue(day({ leads_groups: false, groups: [], review_waiting: { count: 0, oldest_submitted_at: null } }));
    renderPage(<MyDayPage />, { role: "admin" });
    expect(await screen.findByText("У вас нет закреплённых групп.")).toBeInTheDocument();
    expect(screen.queryByText("На проверке")).not.toBeInTheDocument();
  });

  it("ошибка загрузки показана", async () => {
    get.mockRejectedValue(new ApiError(500, "Сбой сервера"));
    renderPage(<MyDayPage />, { role: "curator" });
    expect(await screen.findByText("Сбой сервера")).toBeInTheDocument();
  });

  it("приветствие по времени суток и по имени-отчеству, число дел на сегодня", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 2, 8, 30));
    get.mockResolvedValue(day({
      groups: [{ id: 7, code: "СА172", course: 1, today_status: "pending", is_on_time: null, missed_dates: [], missed_total: 0 }],
      tasks: [{ assignment_id: 11, title: "Кружки", group_code: "СА172", due_date: "2026-10-02", kind: "due_soon", status: "new", days_left: 0 }],
    }));
    renderPage(<MyDayPage />, { role: "curator", user: { full_name: "Иванова Анна Ивановна" } });
    expect(await screen.findByRole("heading", { name: "Доброе утро, Анна Ивановна" })).toBeInTheDocument();
    expect(screen.getByText("2 дела на сегодня")).toBeInTheDocument();
  });

  it("несданный сегодня день — крупная кнопка отметки для группы", async () => {
    get.mockResolvedValue(day({
      groups: [{ id: 7, code: "СА172", course: 1, today_status: "pending", is_on_time: null, missed_dates: [], missed_total: 0 }],
    }));
    renderPage(<MyDayPage />, { role: "curator" });
    expect(await screen.findByRole("link", { name: "Отметить посещаемость СА172" })).toHaveAttribute("href", "/cabinet?group=7");
  });

  it("ритм группы: столбик на день с подписью и общая сводка для диктора", async () => {
    get.mockResolvedValue(day({
      groups: [{
        id: 7, code: "СА172", course: 1, today_status: "submitted", is_on_time: true, missed_dates: [], missed_total: 0,
        rhythm: [
          { date: "2026-09-30", kind: "ok", absent: 0 },
          { date: "2026-10-01", kind: "absent", absent: 2 },
          { date: "2026-10-02", kind: "missing", absent: 0 },
          { date: "2026-10-03", kind: "off", absent: 0 },
        ],
      }],
    }));
    renderPage(<MyDayPage />, { role: "curator" });
    const rhythm = await screen.findByRole("img", { name: "Ритм за 4 дня: учебных 3, с пропусками без причины 1, не сдано 1" });
    expect(rhythm.querySelector('[title="01.10: пропуски без причины — 2"]')).not.toBeNull();
    expect(screen.getByText("занятий нет", { selector: ".rhythm-legend__item" })).toBeInTheDocument();
  });
});
