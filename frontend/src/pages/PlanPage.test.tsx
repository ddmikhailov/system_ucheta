import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, downloadFile } from "../api/client";
import type { GroupEvent, GroupMeetings, GroupPlan, ParentMeeting } from "../api/types";
import { renderPage } from "../test/utils";
import PlanPage from "./PlanPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }, downloadFile: vi.fn() };
});

vi.mock("../utils/feedback", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../utils/feedback")>();
  return { ...actual, dialogs: { ...actual.dialogs, confirm: vi.fn().mockResolvedValue(true) } };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);
const put = vi.mocked(api.put);
const del = vi.mocked(api.delete);
const download = vi.mocked(downloadFile);

const SECTIONS = [
  { key: "civic", title: "Гражданско - патриотическое воспитание" },
  { key: "legal", title: "Правовое воспитание, профилактика правонарушений" },
  { key: "group_org", title: "Организационные мероприятия в группе" },
];

function event(over: Partial<GroupEvent> = {}): GroupEvent {
  return {
    id: 1, study_group_id: 7, school_year: "2026-2027", section: "civic", title: "Урок мужества", event_date: "2026-10-14",
    time_text: "14:30", responsible: "Куратор", goal: "Патриотизм", status: "planned", result: null, is_class_hour: false,
    description: null, attendee_ids: [], ...over,
  };
}

function plan(events: GroupEvent[], over: Partial<GroupPlan> = {}): GroupPlan {
  return {
    group_id: 7, group_code: "СА172", school_year: "2026-2027", years: ["2026-2027", "2025-2026"], sections: SECTIONS, events,
    students: [{ id: 1, full_name: "Алексеев Пётр" }, { id: 2, full_name: "Андреева Елена" }, { id: 3, full_name: "Борисов Иван" }],
    can_edit: true, ...over,
  };
}

let meetings: GroupMeetings = { group_id: 7, school_year: "2026-2027", meetings: [], guardians: [] };

function meeting(over: Partial<ParentMeeting> = {}): ParentMeeting {
  return {
    id: 3, study_group_id: 7, school_year: "2026-2027", number: 1, meeting_date: "2026-10-02", agenda: "Итоги месяца\nПосещаемость",
    staff: null, speakers: null, meeting_format: "in_person", parents_count: null, listened: null, resolved: null, attendee_ids: [], ...over,
  };
}

function mock(p: GroupPlan, m: GroupMeetings = { group_id: 7, school_year: p.school_year, meetings: [], guardians: [] }) {
  meetings = m;
  get.mockImplementation(async (path: string) => {
    if (path === "/individual-work/groups") return [{ id: 7, code: "СА172", course: 1 }];
    if (path.startsWith("/events/groups/7")) return p;
    if (path.startsWith("/meetings/groups/7")) return meetings;
    throw new Error(`неожиданный запрос ${path}`);
  });
}

beforeEach(() => {
  for (const m of [get, post, put, del, download]) m.mockReset();
  download.mockResolvedValue(undefined);
  del.mockResolvedValue(undefined);
});

describe("PlanPage — план воспитательной работы группы", () => {
  it("показывает разделы бланка и мероприятия: дата, цель, результат, отметка о выполнении", async () => {
    mock(plan([event(), event({ id: 2, title: "Беседа о праве", section: "legal", status: "done", result: "Прошла хорошо", event_date: null })]));
    renderPage(<PlanPage />, { role: "curator" });
    const row = (await screen.findByText("Урок мужества")).closest("tr") as HTMLElement;
    expect(get).toHaveBeenCalledWith("/events/groups/7");
    expect(within(row).getByText("14.10.2026")).toBeInTheDocument();
    expect(within(row).getByText("Цель: Патриотизм")).toBeInTheDocument();
    expect(within(row).getByText("Запланировано")).toBeInTheDocument();
    const legal = screen.getByText("Беседа о праве").closest("tr") as HTMLElement;
    expect(within(legal).getByText("Проведено")).toBeInTheDocument();
    expect(within(legal).getByText("Прошла хорошо")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Организационные мероприятия в группе/ })).toBeInTheDocument();
  });

  it("добавляет мероприятие: раздел по умолчанию — тот, где нажали, год без даты — выбранный", async () => {
    const user = userEvent.setup();
    mock(plan([]));
    post.mockResolvedValue(event());
    renderPage(<PlanPage />, { role: "curator" });
    await screen.findByRole("heading", { name: /Правовое воспитание/ });
    const legal = screen.getByRole("heading", { name: /Правовое воспитание/ }).closest("section") as HTMLElement;
    await user.click(within(legal).getByRole("button", { name: "+ Добавить в раздел" }));
    const dialog = await screen.findByRole("dialog", { name: "Мероприятие плана" });
    expect(within(dialog).getByLabelText("Раздел плана")).toHaveValue("legal");
    await user.type(within(dialog).getByLabelText("Наименование мероприятия"), "Встреча с инспектором");
    await user.type(within(dialog).getByLabelText("Ответственные за проведение"), "Куратор");
    await user.click(within(dialog).getByRole("button", { name: "Сохранить" }));
    expect(post).toHaveBeenCalledWith("/events/groups/7", expect.objectContaining({
      section: "legal", title: "Встреча с инспектором", responsible: "Куратор", status: "planned", event_date: null,
      is_class_hour: false, school_year: "2026-2027",
    }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Мероприятие плана" })).not.toBeInTheDocument());
  });

  it("классный час: описание появляется только после галочки; результат — когда мероприятие уже не «запланировано»", async () => {
    const user = userEvent.setup();
    mock(plan([event()]));
    put.mockResolvedValue(event());
    renderPage(<PlanPage />, { role: "curator" });
    await user.click(await screen.findByRole("button", { name: "Изменить" }));
    const dialog = await screen.findByRole("dialog", { name: "Мероприятие плана" });
    expect(within(dialog).queryByLabelText(/Формат и описание/)).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText(/Результат/)).not.toBeInTheDocument();
    await user.selectOptions(within(dialog).getByLabelText("Отметка о выполнении"), "done");
    await user.type(within(dialog).getByLabelText(/Результат/), "Все активны");
    await user.click(within(dialog).getByLabelText(/Классный час/));
    await user.type(within(dialog).getByLabelText(/Формат и описание/), "Очно, беседа");
    await user.click(within(dialog).getByRole("button", { name: "Сохранить" }));
    expect(put).toHaveBeenCalledWith("/events/1", expect.objectContaining({
      status: "done", result: "Все активны", is_class_hour: true, description: "Очно, беседа", event_date: "2026-10-14",
    }));
  });

  it("присутствующие на классном часе: по умолчанию все, снимаем одного, список уходит на сервер", async () => {
    const user = userEvent.setup();
    mock(plan([event({ id: 5, title: "Классный час", section: "group_org", is_class_hour: true })]));
    put.mockResolvedValue(event());
    renderPage(<PlanPage />, { role: "curator" });
    const row = (await screen.findByText("Классный час", { selector: "td" })).closest("tr") as HTMLElement;
    expect(within(row).getByText("Присутствовало: не отмечено")).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Присутствующие" }));
    const dialog = await screen.findByRole("dialog", { name: "Присутствующие на классном часе" });
    expect(within(dialog).getByText("Присутствует: 3 из 3")).toBeInTheDocument();
    await user.click(within(dialog).getByLabelText("Борисов Иван"));
    await user.click(within(dialog).getByRole("button", { name: "Сохранить" }));
    expect(put).toHaveBeenCalledWith("/events/5/attendance", { student_ids: [1, 2] });
  });

  it("Word: план группы, план куратора и протокол классного часа", async () => {
    const user = userEvent.setup();
    mock(plan([event({ id: 5, title: "Классный час", section: "group_org", is_class_hour: true, attendee_ids: [1, 2] })]));
    renderPage(<PlanPage />, { role: "curator" });
    await screen.findByText("Присутствовало: 2 из 3");
    await user.click(screen.getByRole("button", { name: "План группы в Word" }));
    expect(download).toHaveBeenCalledWith("/events/groups/7/plan.docx?kind=group&year=2026-2027", "План_группы_СА172.docx");
    await user.click(screen.getByRole("button", { name: "План куратора в Word" }));
    expect(download).toHaveBeenCalledWith("/events/groups/7/plan.docx?kind=curator&year=2026-2027", "План_куратора_СА172.docx");
    await user.click(screen.getByRole("button", { name: "Протокол в Word" }));
    expect(download).toHaveBeenCalledWith("/events/5/protocol.docx", "Протокол_классного_часа_СА172.docx");
  });

  it("удаляет мероприятие после подтверждения", async () => {
    const user = userEvent.setup();
    mock(plan([event()]));
    renderPage(<PlanPage />, { role: "curator" });
    await user.click(await screen.findByRole("button", { name: "Удалить" }));
    expect(del).toHaveBeenCalledWith("/events/1");
  });

  it("только чтение: кнопок правки нет, а выгрузка в Word есть", async () => {
    mock(plan([event({ id: 5, is_class_hour: true })], { can_edit: false }));
    renderPage(<PlanPage />, { role: "social_pedagogue" });
    await screen.findByText("Урок мужества");
    expect(screen.queryByRole("button", { name: "Добавить мероприятие" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Изменить" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Удалить" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Присутствующие" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "План группы в Word" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Протокол в Word" })).toBeInTheDocument();
  });

  it("учебный год переключается; ошибка загрузки показывается", async () => {
    const user = userEvent.setup();
    mock(plan([event()]));
    renderPage(<PlanPage />, { role: "curator" });
    await user.selectOptions(await screen.findByLabelText("Учебный год"), "2025-2026");
    await waitFor(() => expect(get).toHaveBeenCalledWith("/events/groups/7?year=2025-2026"));

    get.mockReset();
    get.mockImplementation(async (path: string) => {
      if (path === "/individual-work/groups") return [{ id: 7, code: "СА172", course: 1 }];
      throw new ApiError(403, "Это не ваша группа");
    });
    renderPage(<PlanPage />, { role: "curator" });
    expect(await screen.findByText("Это не ваша группа")).toBeInTheDocument();
  });

  it("родительские собрания: список, добавление, отметка родителей, протокол в Word", async () => {
    const user = userEvent.setup();
    const guardians = [
      { id: 11, full_name: "Иванова Мария", relation: "мать", student_name: "Алексеев Пётр" },
      { id: 12, full_name: "Петров Пётр", relation: "отец", student_name: "Андреева Елена" },
    ];
    mock(plan([]), { group_id: 7, school_year: "2026-2027", meetings: [meeting({ attendee_ids: [11] }), meeting({ id: 4, number: 2, meeting_date: null, parents_count: 17, meeting_format: "remote", agenda: null })], guardians });
    post.mockResolvedValue(meeting());
    put.mockResolvedValue(meeting());
    renderPage(<PlanPage />, { role: "curator" });

    const first = (await screen.findByText(/Итоги месяца/)).closest("tr") as HTMLElement;
    expect(within(first).getByText("02.10.2026")).toBeInTheDocument();
    expect(within(first).getByText("очно")).toBeInTheDocument();
    const second = screen.getByText("дистанционно").closest("tr") as HTMLElement;
    expect(within(second).getByText("17")).toBeInTheDocument(); // число без поимённой отметки

    await user.click(within(first).getByRole("button", { name: "Протокол собрания в Word" }));
    expect(download).toHaveBeenCalledWith("/meetings/3/protocol.docx", "Протокол_родительского_собрания_СА172.docx");

    await user.click(within(first).getByRole("button", { name: "Присутствующие родители" }));
    const attendance = await screen.findByRole("dialog", { name: "Присутствующие родители" });
    expect(within(attendance).getByLabelText(/Иванова Мария/)).toBeChecked();
    await user.click(within(attendance).getByLabelText(/Петров Пётр/));
    await user.click(within(attendance).getByRole("button", { name: "Сохранить" }));
    expect(put).toHaveBeenCalledWith("/meetings/3/attendance", { guardian_ids: [11, 12] });

    await user.click(screen.getByRole("button", { name: "+ Добавить родительское собрание" }));
    const form = await screen.findByRole("dialog", { name: "Родительское собрание" });
    await user.type(within(form).getByLabelText(/Повестка/), "Итоги четверти");
    await user.selectOptions(within(form).getByLabelText("Формат проведения"), "remote");
    await user.click(within(form).getByRole("button", { name: "Сохранить" }));
    expect(post).toHaveBeenCalledWith("/meetings/groups/7", expect.objectContaining({
      agenda: "Итоги четверти", meeting_format: "remote", meeting_date: null, number: null, school_year: "2026-2027",
    }));
  });

  it("у собраний только чтение: правки нет, протокол есть; без представителей в досье — подсказка", async () => {
    const user = userEvent.setup();
    mock(plan([], { can_edit: false }), { group_id: 7, school_year: "2026-2027", meetings: [meeting()], guardians: [] });
    renderPage(<PlanPage />, { role: "psychologist" });
    await screen.findByText(/Итоги месяца/);
    expect(screen.queryByRole("button", { name: "+ Добавить родительское собрание" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Присутствующие родители" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Удалить собрание" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Протокол собрания в Word" })).toBeInTheDocument();
    void user;
  });

  it("собраний нет — подсказка; удаление собрания после подтверждения", async () => {
    const user = userEvent.setup();
    mock(plan([]));
    renderPage(<PlanPage />, { role: "curator" });
    expect(await screen.findByText("В этом учебном году собраний ещё нет.")).toBeInTheDocument();

    mock(plan([]), { group_id: 7, school_year: "2026-2027", meetings: [meeting()], guardians: [] });
    renderPage(<PlanPage />, { role: "curator" });
    await user.click(await screen.findByRole("button", { name: "Удалить собрание" }));
    expect(del).toHaveBeenCalledWith("/meetings/3");
  });
});
