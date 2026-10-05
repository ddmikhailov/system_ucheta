import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, downloadFile } from "../api/client";
import type { AssignmentDetail, TaskDetail, TaskListRow } from "../api/types";
import FeedbackHost from "../components/FeedbackHost";
import { dialogs, resetFeedback } from "../utils/feedback";
import { renderPage } from "../test/utils";
import { REVIEWER_LABELS } from "../constants/tasks";
import TasksPage from "./TasksPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }, downloadFile: vi.fn() };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);
const patch = vi.mocked(api.patch);
const del = vi.mocked(api.delete);
const download = vi.mocked(downloadFile);

const progress = { total: 46, new: 40, in_progress: 2, submitted: 3, returned: 0, accepted: 1, overdue: 2 };

const LIST: TaskListRow[] = [
  { id: 1, title: "Кружки доп. образования", collect_mode: "student", reviewer_rule: "dept_head", due_date: "2026-10-06", is_closed: false, author_name: "Админ А.", progress, step_no: 1, step_total: null },
  { id: 2, title: "Видеовизитка", collect_mode: "group", reviewer_rule: "two_step", due_date: "2026-10-14", is_closed: true, author_name: "Админ А.", progress: { ...progress, overdue: 0 }, step_no: 1, step_total: null },
];

const DETAIL: TaskDetail = {
  id: 1, title: "Кружки доп. образования", description: "Собрать кружки", collect_mode: "student", reviewer_rule: "dept_head",
  due_date: "2026-10-06", is_closed: false, author_id: 1, author_name: "Админ А.",
  fields: [{ key: "f1", label: "Телефон", type: "text", required: true, options: [] }],
  scope: { all_groups: true, department_ids: [], courses: [], group_ids: [], exclude_group_ids: [] },
  can_manage: true, progress, step_no: 1, unlock_on: null, steps: [],
  assignments: [
    { id: 10, study_group_id: 1, group_code: "СА172", course: 1, department_name: "Диджитал", status: "submitted", is_overdue: false, submitted_at: "2026-10-01T09:00:00", reviewed_at: null, reviewed_by_name: null },
    { id: 11, study_group_id: 2, group_code: "ИИ112", course: 1, department_name: "Диджитал", status: "new", is_overdue: true, submitted_at: null, reviewed_at: null, reviewed_by_name: null },
    { id: 12, study_group_id: 3, group_code: "ИТ201", course: 2, department_name: "Диджитал", status: "accepted", is_overdue: false, submitted_at: null, reviewed_at: null, reviewed_by_name: null },
  ],
};

const DOSSIER_TARGETS = [
  { key: "phone", label: "Телефон студента", types: ["text"] },
  { key: "funding", label: "Финансирование (бюджет/договор)", types: ["select"] },
  { key: "additional_education", label: "Дополнительное образование", types: ["text", "multiselect"] },
];

let templates: object[] = [];

const TEMPLATE = {
  id: 4, name: "Ежегодная сверка", author_name: "Админ", created_at: "2026-09-01T10:00:00", can_manage: true,
  title: "Сверка контактов", description: "Проверить телефоны", collect_mode: "selected", reviewer_rule: "two_step",
  fields: [
    { key: "f1", label: "Телефон", type: "text", required: true, options: [], dossier_field: "phone" },
    { key: "f2", label: "Кружки", type: "multiselect", required: false, options: ["Спорт", "Танцы"], dossier_field: null },
  ],
  scope: { all_groups: false, department_ids: [], courses: [1, 2], group_ids: [], exclude_group_ids: [5] },
};

function mockApi(over: { list?: TaskListRow[]; queue?: object[]; detail?: TaskDetail } = {}) {
  get.mockImplementation(async (path: string) => {
    if (path === "/tasks") return over.list ?? LIST;
    if (path === "/tasks/review-queue") return over.queue ?? [];
    if (path === "/tasks/dossier-fields") return DOSSIER_TARGETS;
    if (path === "/tasks/templates") return templates;
    if (path.startsWith("/tasks/")) return over.detail ?? DETAIL;
    if (path === "/admin/departments") return [{ id: 1, name: "Диджитал", is_active: true }, { id: 2, name: "Моссовет", is_active: true }];
    if (path === "/admin/groups") return [{ id: 1, code: "СА172", course: 1, is_active: true }, { id: 2, code: "ИИ112", course: 1, is_active: true }];
    throw new Error(`неожиданный запрос ${path}`);
  });
}

/** Страница вместе с хостом диалогов и сообщений — как в приложении. */
function withFeedback(ui: ReactElement) {
  return (
    <>
      {ui}
      <FeedbackHost />
    </>
  );
}

beforeEach(() => {
  // «Сегодня» — 4 октября 2026: от него считаются «через N дней».
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 9, 4, 10, 0));
  templates = [];
  for (const fn of [get, post, patch, del, download]) fn.mockReset();
  download.mockResolvedValue(undefined);
});

afterEach(() => {
  vi.useRealTimers();
  resetFeedback();
});

describe("TasksPage — список", () => {
  it("задачи с полосой прогресса, просрочкой и сроком словами; закрытые — в своём фильтре", async () => {
    const user = userEvent.setup();
    mockApi();
    renderPage(<TasksPage />, { role: "admin" });
    const first = (await screen.findByRole("button", { name: "Кружки доп. образования" })).closest("li") as HTMLElement;
    expect(within(first).getByText("сдано 4 из 46")).toBeInTheDocument();
    expect(within(first).getByText("просрочено 2")).toBeInTheDocument();
    expect(within(first).getByRole("img", { name: /Из 46 групп: принято 1, на проверке 3, в работе 2, не начато 40/ })).toBeInTheDocument();
    expect(within(first).getByText("через 2 дня")).toBeInTheDocument();
    expect(within(first).getByText("вт 06.10")).toBeInTheDocument();
    expect(screen.queryByText("Видеовизитка")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Закрытые 1" }));
    const closed = screen.getByRole("button", { name: "Видеовизитка" }).closest("li") as HTMLElement;
    expect(within(closed).getByText("закрыта")).toBeInTheDocument();
    expect(within(closed).getByText("14.10.2026")).toBeInTheDocument();
  });

  it("фильтры «Мои» и «С просрочкой»", async () => {
    const user = userEvent.setup();
    mockApi({
      list: [
        { ...LIST[0], id: 1, title: "Моя", author_id: 1 },
        { ...LIST[0], id: 3, title: "Чужая без просрочки", author_id: 2, progress: { ...progress, overdue: 0 } },
      ],
    });
    renderPage(<TasksPage />, { role: "admin", user: { id: 1 } });
    await screen.findByText("Моя");
    await user.click(screen.getByRole("button", { name: "Мои 1" }));
    expect(screen.queryByText("Чужая без просрочки")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "С просрочкой 1" }));
    expect(screen.getByText("Моя")).toBeInTheDocument();
    expect(screen.queryByText("Чужая без просрочки")).not.toBeInTheDocument();
  });

  it("у шагов цепочки видно «шаг N из M»", async () => {
    mockApi({ list: [{ ...LIST[0], step_no: 2, step_total: 3 }, LIST[1]] });
    renderPage(<TasksPage />, { role: "admin" });
    expect(await screen.findByText("шаг 2 из 3")).toBeInTheDocument();
  });

  it("клик по названию открывает карточку", async () => {
    const user = userEvent.setup();
    mockApi();
    renderPage(<TasksPage />, { role: "admin", route: "/tasks", path: "/tasks" });
    await user.click(await screen.findByRole("button", { name: "Кружки доп. образования" }));
    expect(await screen.findByRole("heading", { name: "Кружки доп. образования" })).toBeInTheDocument();
  });

  it("пустой список подсказывает создать задачу", async () => {
    mockApi({ list: [] });
    renderPage(<TasksPage />, { role: "admin" });
    expect(await screen.findByText(/Задач пока нет/)).toBeInTheDocument();
  });

  it("ошибка загрузки списка показывается", async () => {
    get.mockRejectedValue(new ApiError(500, "Сервер недоступен"));
    renderPage(<TasksPage />, { role: "admin" });
    expect(await screen.findByText("Сервер недоступен")).toBeInTheDocument();
  });
});

describe("TasksPage — режим проверки", () => {
  const QUEUE = [
    { id: 10, task_id: 1, title: "Кружки доп. образования", group_code: "СА172", department_name: "Диджитал", due_date: "2026-10-06", submitted_at: "2026-10-01T09:00:00", is_overdue: false },
    { id: 11, task_id: 2, title: "Видеовизитка", group_code: "ИИ112", department_name: "Диджитал", due_date: "2026-10-14", submitted_at: "2026-10-02T09:00:00", is_overdue: true },
  ];
  const answer = (id: number, over: Partial<AssignmentDetail> = {}): AssignmentDetail => ({
    id, task_id: 1, title: "Кружки доп. образования", description: null, collect_mode: "student", reviewer_rule: "dept_head",
    due_date: "2026-10-06", is_closed: false, fields: [{ key: "f1", label: "Телефон", type: "text", required: true, options: [] }],
    study_group_id: 1, group_code: "СА172", status: "submitted", is_overdue: false, group_values: {},
    rows: [{ student_id: 1, student_name: "Алексеев Пётр", is_included: true, values: { f1: "+7 900" } }],
    comments: [], review_comment: null, submitted_at: null, reviewed_at: null, reviewed_by_name: null, history: [],
    review_step: 1, review_steps: 1, can_edit: false, can_submit: false, can_review: true, is_locked: false,
    locked_reason: null, step_no: 1, step_total: null, ...over,
  });

  function mockReview() {
    get.mockImplementation(async (path: string) => {
      if (path === "/tasks") return LIST;
      if (path === "/tasks/review-queue") return QUEUE;
      if (path === "/tasks/assignments/10") return answer(10);
      if (path === "/tasks/assignments/11")
        return answer(11, { collect_mode: "group", group_code: "ИИ112", title: "Видеовизитка", rows: [], fields: [{ key: "v", label: "Видео", type: "link", required: true, options: [] }], group_values: { v: "https://vk.com/v1" } });
      throw new Error(`неожиданный запрос ${path}`);
    });
  }

  async function openReview() {
    const user = userEvent.setup();
    mockReview();
    renderPage(<TasksPage />, { role: "dept_head" });
    await user.click(await screen.findByRole("button", { name: "На проверке 2" }));
    return user;
  }

  it("очередь слева, первый ответ открыт справа", async () => {
    await openReview();
    const queue = screen.getByRole("list", { name: "Очередь проверки" });
    expect(within(queue).getAllByRole("button")).toHaveLength(2);
    expect(within(queue).getByText(/после срока/)).toBeInTheDocument();
    const pane = screen.getByRole("region", { name: "Ответ группы" });
    expect(await within(pane).findByText("Алексеев Пётр")).toBeInTheDocument();
    expect(within(pane).getByText("+7 900")).toBeInTheDocument();
    expect(within(pane).getByRole("link", { name: "Открыть целиком" })).toHaveAttribute("href", "/tasks/assignment/10");
  });

  it("«Принять» отправляет решение и открывает следующий ответ", async () => {
    const user = await openReview();
    post.mockResolvedValue({});
    await screen.findByText("Алексеев Пётр");
    await user.click(screen.getByRole("button", { name: "Принять" }));
    expect(post).toHaveBeenCalledWith("/tasks/assignments/10/review", { action: "accept", comment: null });
    expect(await screen.findByRole("link", { name: "https://vk.com/v1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "На проверке 1" })).toBeInTheDocument();
  });

  it("вернуть без комментария нельзя; с комментарием — уходит", async () => {
    const user = await openReview();
    await screen.findByText("Алексеев Пётр");
    await user.click(screen.getByRole("button", { name: "Вернуть" }));
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("без комментария вернуть нельзя");
    post.mockResolvedValue({});
    await user.type(screen.getByRole("textbox", { name: "Комментарий проверяющего" }), "Нет телефона");
    await user.click(screen.getByRole("button", { name: "Вернуть" }));
    expect(post).toHaveBeenCalledWith("/tasks/assignments/10/review", { action: "return", comment: "Нет телефона" });
  });

  it("горячих клавиш нет: случайное нажатие не принимает ответ", async () => {
    const user = await openReview();
    await screen.findByText("Алексеев Пётр");
    await user.click(screen.getByRole("region", { name: "Ответ группы" }));
    await user.keyboard("a");
    expect(post).not.toHaveBeenCalled();
  });

  it("выбор другого ответа в очереди", async () => {
    const user = await openReview();
    await screen.findByText("Алексеев Пётр");
    await user.click(within(screen.getByRole("list", { name: "Очередь проверки" })).getByRole("button", { name: /ИИ112/ }));
    expect(await screen.findByRole("link", { name: "https://vk.com/v1" })).toBeInTheDocument();
  });

  it("пустая очередь", async () => {
    const user = userEvent.setup();
    mockApi();
    renderPage(<TasksPage />, { role: "dept_head" });
    await user.click(await screen.findByRole("button", { name: "На проверке" }));
    expect(await screen.findByText("Ничего не ждёт вашей проверки.")).toBeInTheDocument();
  });
});

describe("TasksPage — карточка задачи", () => {
  const openTask = () => renderPage(withFeedback(<TasksPage />), { route: "/tasks?task=1", role: "admin" });

  it("форма, прогресс и карта групп со ссылками на ответы", async () => {
    mockApi();
    openTask();
    expect(await screen.findByRole("heading", { name: "Кружки доп. образования" })).toBeInTheDocument();
    expect(screen.getByText("Телефон")).toBeInTheDocument();
    expect(screen.getByText("сдано 4 из 46")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "СА172, Диджитал: На проверке" })).toHaveAttribute("href", "/tasks/assignment/10");
    expect(screen.getByRole("link", { name: "ИИ112, Диджитал: Просрочено" })).toBeInTheDocument();
    expect(screen.getByText("1 курс")).toBeInTheDocument();
    expect(screen.getByText("2 курс")).toBeInTheDocument();
  });

  it("таблица: кто принял и когда, когда отправлено; фильтр по статусу", async () => {
    const user = userEvent.setup();
    mockApi({
      detail: {
        ...DETAIL,
        assignments: [
          { ...DETAIL.assignments[2], status: "accepted", reviewed_at: "2026-10-03T12:30:00", reviewed_by_name: "Петрова Н." },
          { ...DETAIL.assignments[0], status: "returned", reviewed_at: "2026-10-02T09:00:00", reviewed_by_name: "Сидоров С." },
          { ...DETAIL.assignments[0], id: 20, group_code: "ИБ301", status: "submitted", submitted_at: "2026-10-01T09:00:00" },
          { ...DETAIL.assignments[1], id: 21, group_code: "ИС401", status: "accepted", reviewed_at: "2026-10-04T08:00:00", reviewed_by_name: null },
          DETAIL.assignments[1],
        ],
      },
    });
    openTask();
    await user.click(await screen.findByRole("button", { name: "Таблица" }));
    const cell = (code: string) => screen.getByRole("link", { name: code }).closest("tr") as HTMLElement;
    expect(cell("ИТ201")).toHaveTextContent(/Принято 03\.10\.2026.*Петрова Н\./);
    expect(cell("СА172")).toHaveTextContent(/Возвращено 02\.10\.2026.*Сидоров С\./);
    expect(cell("ИБ301")).toHaveTextContent(/Отправлено 01\.10\.2026/);
    expect(cell("ИС401")).toHaveTextContent(/Принято 04\.10\.2026.*без проверки/);
    expect(cell("ИИ112")).toHaveTextContent("Не начато, просрочено");

    await user.selectOptions(screen.getByRole("combobox", { name: "Статус" }), "accepted");
    expect(screen.getByRole("link", { name: "ИТ201" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "СА172" })).not.toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox", { name: "Статус" }), "in_progress");
    expect(screen.getByText("Нет групп с таким статусом.")).toBeInTheDocument();
  });

  it("вкладка «Ответы» показывает сводку по вариантам", async () => {
    const user = userEvent.setup();
    mockApi();
    get.mockImplementation(async (path: string) => {
      if (path === "/tasks/1/summary")
        return { groups: 3, answers: 70, fields: [{ key: "f1", label: "Кружки", type: "multiselect", filled: 40, counts: [{ label: "Спорт", count: 30 }, { label: "Танцы", count: 12 }] }] };
      if (path === "/tasks/1") return DETAIL;
      return [];
    });
    openTask();
    await user.click(await screen.findByRole("button", { name: "Ответы" }));
    const field = await screen.findByRole("region", { name: "Кружки" });
    expect(within(field).getByText("Спорт").closest("li")).toHaveTextContent("30");
    expect(screen.getByText(/По 70 студентам из 3 групп/)).toBeInTheDocument();
  });

  it("сводка без отправленных ответов объясняет, когда появится", async () => {
    const user = userEvent.setup();
    get.mockImplementation(async (path: string) => {
      if (path === "/tasks/1/summary") return { groups: 0, answers: 0, fields: [] };
      if (path === "/tasks/1") return DETAIL;
      return [];
    });
    openTask();
    await user.click(await screen.findByRole("button", { name: "Ответы" }));
    expect(await screen.findByText(/Сводка появится, когда группы начнут отправлять ответы/)).toBeInTheDocument();
  });

  it("«Напомнить» считает отстающие группы, спрашивает и сообщает итог", async () => {
    const user = userEvent.setup();
    mockApi();
    post.mockResolvedValue({ sent: 1, skipped: 0 });
    const confirm = vi.spyOn(dialogs, "confirm").mockResolvedValueOnce(false);
    openTask();
    // В DETAIL не отправили ответ одна группа (ИИ112, «не начато»).
    await user.click(await screen.findByRole("button", { name: "Напомнить 1 группе" }));
    expect(confirm).toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();
    confirm.mockResolvedValueOnce(true);
    await user.click(screen.getByRole("button", { name: "Напомнить 1 группе" }));
    expect(post).toHaveBeenCalledWith("/tasks/1/remind");
    expect(await screen.findByText("Напоминание отправлено 1 группе")).toBeInTheDocument();
  });

  it("закрытой задаче и без отстающих напоминать нечего", async () => {
    mockApi({ detail: { ...DETAIL, is_closed: true } });
    const { unmount } = openTask();
    await screen.findByRole("heading", { name: "Кружки доп. образования" });
    expect(screen.queryByRole("button", { name: /Напомнить/ })).not.toBeInTheDocument();
    unmount();

    mockApi({ detail: { ...DETAIL, assignments: [{ ...DETAIL.assignments[1], is_locked: true }] } });
    openTask();
    await screen.findByRole("heading", { name: "Кружки доп. образования" });
    expect(screen.queryByRole("button", { name: /Напомнить/ })).not.toBeInTheDocument();
  });

  it("цепочка шагов: ссылки на другие шаги, «Добавить следующий шаг» только у последнего", async () => {
    const user = userEvent.setup();
    const steps = [
      { id: 1, title: "Сценарий", step_no: 1, due_date: "2026-10-06" },
      { id: 2, title: "Видео", step_no: 2, due_date: "2026-10-20" },
    ];
    mockApi({ detail: { ...DETAIL, id: 1, steps, unlock_on: null } });
    openTask();
    await screen.findByRole("heading", { name: "Кружки доп. образования" });
    expect(screen.getByRole("link", { name: "2. Видео" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "1. Сценарий" })).not.toBeInTheDocument();
    await user.click(screen.getByText("Ещё"));
    expect(screen.queryByRole("button", { name: "Добавить следующий шаг" })).not.toBeInTheDocument();
  });

  it("последний шаг: когда открывается, и предложение следующего", async () => {
    const user = userEvent.setup();
    const steps = [
      { id: 1, title: "Сценарий", step_no: 1, due_date: "2026-10-06" },
      { id: 2, title: "Видео", step_no: 2, due_date: "2026-10-20" },
    ];
    mockApi({ detail: { ...DETAIL, id: 2, step_no: 2, steps, unlock_on: "accepted" } });
    openTask();
    expect(await screen.findByText(/открывается после приёмки предыдущего/)).toBeInTheDocument();
    await user.click(screen.getByText("Ещё"));
    expect(screen.getByRole("button", { name: "Добавить следующий шаг" })).toBeInTheDocument();
  });

  it("управление — только автору/админу; выгрузка и шаблон — всем", async () => {
    const user = userEvent.setup();
    mockApi({ detail: { ...DETAIL, can_manage: false } });
    openTask();
    await screen.findByRole("heading", { name: "Кружки доп. образования" });
    expect(screen.getByRole("button", { name: "Выгрузить в Excel" })).toBeInTheDocument();
    await user.click(screen.getByText("Ещё"));
    expect(screen.getByRole("button", { name: "Сохранить как шаблон" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Закрыть задачу" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Удалить" })).not.toBeInTheDocument();
  });

  it("«Сохранить как шаблон»: спрашивает название, сохраняет и сообщает", async () => {
    const user = userEvent.setup();
    mockApi({ detail: { ...DETAIL, can_manage: false } });
    post.mockResolvedValue({});
    const prompt = vi.spyOn(dialogs, "prompt").mockResolvedValue("Ежегодная сверка");
    openTask();
    await screen.findByRole("heading", { name: "Кружки доп. образования" });
    await user.click(screen.getByText("Ещё"));
    await user.click(screen.getByRole("button", { name: "Сохранить как шаблон" }));
    expect(prompt).toHaveBeenCalledWith("Название шаблона", "Кружки доп. образования", { confirmLabel: "Сохранить шаблон" });
    expect(post).toHaveBeenCalledWith("/tasks/templates", { task_id: DETAIL.id, name: "Ежегодная сверка" });
    expect(await screen.findByText(/Шаблон «Ежегодная сверка» сохранён/)).toBeInTheDocument();
  });

  it("отмена названия ничего не сохраняет; ошибка сервера показывается", async () => {
    const user = userEvent.setup();
    mockApi();
    const prompt = vi.spyOn(dialogs, "prompt").mockResolvedValueOnce(null);
    openTask();
    await screen.findByRole("heading", { name: "Кружки доп. образования" });
    await user.click(screen.getByText("Ещё"));
    await user.click(screen.getByRole("button", { name: "Сохранить как шаблон" }));
    expect(post).not.toHaveBeenCalled();
    prompt.mockResolvedValueOnce("X");
    post.mockRejectedValueOnce(new ApiError(403, "Нет доступа к этой задаче"));
    await user.click(screen.getByText("Ещё"));
    await user.click(screen.getByRole("button", { name: "Сохранить как шаблон" }));
    // Ошибка — и в карточке, и сообщением внизу экрана.
    expect(await screen.findAllByText("Нет доступа к этой задаче")).toHaveLength(2);
  });

  it("закрывает задачу и перезагружает карточку", async () => {
    const user = userEvent.setup();
    mockApi();
    patch.mockResolvedValue({});
    openTask();
    await screen.findByRole("heading", { name: "Кружки доп. образования" });
    await user.click(screen.getByText("Ещё"));
    await user.click(screen.getByRole("button", { name: "Закрыть задачу" }));
    expect(patch).toHaveBeenCalledWith("/tasks/1", { is_closed: true });
    await waitFor(() => expect(get.mock.calls.filter((c) => c[0] === "/tasks/1").length).toBeGreaterThanOrEqual(2));
  });

  it("удаление спрашивает подтверждение; ошибка сервера показывается", async () => {
    const user = userEvent.setup();
    mockApi();
    const confirm = vi.spyOn(dialogs, "confirm").mockResolvedValueOnce(false);
    openTask();
    await screen.findByRole("heading", { name: "Кружки доп. образования" });
    await user.click(screen.getByText("Ещё"));
    await user.click(screen.getByRole("button", { name: "Удалить" }));
    expect(confirm).toHaveBeenCalledWith("Удалить задачу «Кружки доп. образования»?", { confirmLabel: "Удалить", danger: true });
    expect(del).not.toHaveBeenCalled();

    confirm.mockResolvedValueOnce(true);
    del.mockRejectedValue(new ApiError(400, "По задаче уже есть ответы — закройте её вместо удаления"));
    await user.click(screen.getByText("Ещё"));
    await user.click(screen.getByRole("button", { name: "Удалить" }));
    expect(del).toHaveBeenCalledWith("/tasks/1");
    expect(await screen.findAllByText(/закройте её вместо удаления/)).toHaveLength(2);
  });

  it("выгрузка скачивает файл задачи", async () => {
    const user = userEvent.setup();
    mockApi();
    openTask();
    await user.click(await screen.findByRole("button", { name: "Выгрузить в Excel" }));
    expect(download).toHaveBeenCalledWith("/tasks/1/export", "task_1.xlsx");
  });

  it("нет доступа к задаче — сообщение и возврат к списку", async () => {
    const user = userEvent.setup();
    get.mockImplementation(async (path: string) => {
      if (path === "/tasks/7") throw new ApiError(403, "Нет доступа к этой задаче");
      if (path === "/tasks") return LIST;
      return [];
    });
    renderPage(<TasksPage />, { route: "/tasks?task=7", role: "dept_head" });
    expect(await screen.findByText("Нет доступа к этой задаче")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /К списку задач/ }));
    expect(await screen.findByText("Кружки доп. образования")).toBeInTheDocument();
  });
});

describe("TasksPage — мастер создания задачи", () => {
  const PREVIEW = { groups: 2, students: 50, curators: 2, without_curator: [] as string[] };

  async function openForm(role = "admin") {
    const user = userEvent.setup();
    mockApi();
    post.mockImplementation(async (path: string) => {
      if (path === "/tasks/scope-preview") return PREVIEW;
      return { ...DETAIL, id: 1 };
    });
    renderPage(<TasksPage />, { role });
    await user.click(await screen.findByRole("button", { name: "+ Новая задача" }));
    return user;
  }

  const next = (user: ReturnType<typeof userEvent.setup>, label: RegExp = /^Дальше/) => user.click(screen.getByRole("button", { name: label }));
  const created = () => post.mock.calls.find((c) => c[0] === "/tasks") as [string, Record<string, unknown>] | undefined;

  it("проходит четыре шага и отправляет охват, режим, проверяющего и форму ответа", async () => {
    const user = await openForm();
    await user.type(screen.getByRole("textbox", { name: "Название" }), "Флюорография");
    await user.type(screen.getByRole("textbox", { name: "Что нужно сделать и как" }), "Справки у всех");
    await next(user);

    await user.click(screen.getByRole("radio", { name: /Курсы/ }));
    await user.click(screen.getByLabelText(/1 курс/));
    await user.click(screen.getByLabelText(/2 курс/));
    await next(user);

    await user.type(screen.getByRole("textbox", { name: "Название поля 1" }), "Дата справки");
    await user.selectOptions(screen.getByRole("combobox", { name: "Тип поля 1" }), "date");
    await user.click(screen.getByLabelText(/Обязательное/));
    await next(user);

    await user.click(screen.getByRole("radio", { name: /Две ступени/ }));
    await user.click(screen.getByRole("button", { name: "Создать и разослать" }));

    const [, body] = created()!;
    expect(body).toMatchObject({
      title: "Флюорография",
      description: "Справки у всех",
      collect_mode: "student",
      reviewer_rule: "two_step",
      fields: [{ label: "Дата справки", type: "date", required: true, options: [] }],
      scope: { all_groups: false, department_ids: [], courses: [1, 2], group_ids: [], exclude_group_ids: [] },
    });
  });

  it("счётчик охвата показывает группы, студентов, кураторов и группы без куратора", async () => {
    const user = await openForm();
    post.mockImplementation(async (path: string) =>
      path === "/tasks/scope-preview" ? { groups: 44, students: 989, curators: 24, without_curator: ["ИИ132", "СА332"] } : DETAIL
    );
    await user.type(screen.getByRole("textbox", { name: "Название" }), "Кружки");
    await next(user);
    const count = await screen.findByRole("status");
    expect(count).toHaveTextContent("44 группы, 989 студентов, 24 куратора получат задачу.");
    expect(count).toHaveTextContent("Без куратора: ИИ132, СА332");
    expect(post).toHaveBeenCalledWith("/tasks/scope-preview", { all_groups: true, department_ids: [], courses: [], group_ids: [], exclude_group_ids: [] });
  });

  it("не пускает дальше без названия, курса и имени поля — и объясняет почему", async () => {
    const user = await openForm();
    await next(user);
    expect(screen.getByRole("alert")).toHaveTextContent("Назовите задачу");
    await user.type(screen.getByRole("textbox", { name: "Название" }), "Опрос");
    await next(user);
    await user.click(screen.getByRole("radio", { name: /Курсы/ }));
    await next(user);
    expect(screen.getByRole("alert")).toHaveTextContent("Отметьте хотя бы один курс");
    await user.click(screen.getByLabelText(/3 курс/));
    await next(user);
    await next(user);
    expect(screen.getByRole("alert")).toHaveTextContent("Назовите поле 1");
    expect(created()).toBeUndefined();
  });

  it("поле выбора требует варианты и разбивает их по запятым", async () => {
    const user = await openForm();
    await user.type(screen.getByRole("textbox", { name: "Название" }), "Кружки");
    await next(user);
    await next(user);
    await user.type(screen.getByRole("textbox", { name: "Название поля 1" }), "Что посещает");
    await user.selectOptions(screen.getByRole("combobox", { name: "Тип поля 1" }), "multiselect");
    await next(user);
    expect(screen.getByRole("alert")).toHaveTextContent("Перечислите варианты для поля «Что посещает»");
    await user.type(screen.getByRole("textbox", { name: "Варианты поля 1" }), "Спорт, Танцы ,, Шахматы");
    await next(user);
    await user.click(screen.getByRole("button", { name: "Создать и разослать" }));
    expect(created()![1]).toMatchObject({ fields: [{ label: "Что посещает", type: "multiselect", options: ["Спорт", "Танцы", "Шахматы"] }] });
  });

  it("превью показывает, как задачу увидит куратор: название, режим, поле", async () => {
    const user = await openForm();
    await user.type(screen.getByRole("textbox", { name: "Название" }), "Согласия");
    const preview = screen.getByRole("complementary", { name: "Так увидит куратор" });
    expect(within(preview).getByText("Согласия")).toBeInTheDocument();
    await next(user);
    await next(user);
    await user.click(screen.getByRole("radio", { name: /Ответ по группе/ }));
    await user.type(screen.getByRole("textbox", { name: "Название поля 1" }), "Подписано");
    await user.selectOptions(screen.getByRole("combobox", { name: "Тип поля 1" }), "bool");
    expect(within(preview).getByText("Ответ по группе")).toBeInTheDocument();
    expect(within(preview).getByRole("group", { name: "Пример: Подписано" })).toBeInTheDocument();
  });

  it("у зав. отделением нет выбора отделений, охват по умолчанию — своё отделение", async () => {
    const user = await openForm("dept_head");
    await user.type(screen.getByRole("textbox", { name: "Название" }), "Опрос");
    await next(user);
    expect(screen.getByRole("radio", { name: /Всё моё отделение/ })).toBeChecked();
    expect(screen.queryByRole("radio", { name: /Отделения/ })).not.toBeInTheDocument();
  });

  it("поля формы можно добавлять, двигать и убирать (последнее убрать нельзя)", async () => {
    const user = await openForm();
    await user.type(screen.getByRole("textbox", { name: "Название" }), "Опрос");
    await next(user);
    await next(user);
    const removeButtons = () => screen.getAllByRole("button", { name: /^Убрать поле/ });
    expect(removeButtons()[0]).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "+ Добавить поле" }));
    const names = () => screen.getAllByPlaceholderText("Название поля") as HTMLInputElement[];
    await user.type(names()[0], "Первое");
    await user.type(names()[1], "Второе");
    await user.click(screen.getByRole("button", { name: "Поле 1 ниже" }));
    expect(names().map((n) => n.value)).toEqual(["Второе", "Первое"]);
    await user.click(removeButtons()[0]);
    expect(names().map((n) => n.value)).toEqual(["Первое"]);
    expect(removeButtons()[0]).toBeDisabled();
  });

  it("ошибка сервера показывается, введённое остаётся", async () => {
    const user = await openForm();
    post.mockImplementation(async (path: string) => {
      if (path === "/tasks/scope-preview") return PREVIEW;
      throw new ApiError(400, "В охват не попала ни одна группа");
    });
    await user.type(screen.getByRole("textbox", { name: "Название" }), "Опрос");
    await next(user);
    await next(user);
    await user.type(screen.getByRole("textbox", { name: "Название поля 1" }), "Ответ");
    await next(user);
    await user.click(screen.getByRole("button", { name: "Создать и разослать" }));
    expect(await screen.findByText("В охват не попала ни одна группа")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /1\. Что сделать/ }));
    expect(screen.getByRole("textbox", { name: "Название" })).toHaveValue("Опрос");
  });

  it("связь поля с досье: подставляются тип и название, уходит dossier_field; у ответа по группе связи нет", async () => {
    const user = await openForm();
    await user.type(screen.getByRole("textbox", { name: "Название" }), "Контакты");
    await next(user);
    await next(user);
    await user.selectOptions(screen.getByLabelText("Записать в досье, поле 1"), "phone");
    expect(screen.getByRole("textbox", { name: "Название поля 1" })).toHaveValue("Телефон студента");
    await user.selectOptions(screen.getByLabelText("Записать в досье, поле 1"), "funding");
    expect(screen.getByRole("combobox", { name: "Тип поля 1" })).toHaveValue("select");
    expect(screen.getByRole("textbox", { name: "Варианты поля 1" })).toHaveValue("бюджет, договор");
    await user.selectOptions(screen.getByLabelText("Записать в досье, поле 1"), "phone");
    await user.selectOptions(screen.getByRole("combobox", { name: "Тип поля 1" }), "number");
    expect(screen.getByLabelText("Записать в досье, поле 1")).toHaveValue("");
    await user.selectOptions(screen.getByRole("combobox", { name: "Тип поля 1" }), "text");
    await user.selectOptions(screen.getByLabelText("Записать в досье, поле 1"), "phone");
    await next(user);
    await user.click(screen.getByRole("button", { name: "Создать и разослать" }));
    expect(created()![1]).toMatchObject({ fields: [expect.objectContaining({ label: "Телефон студента", type: "text", dossier_field: "phone" })] });
  });

  it("в задаче «по группе» связи с досье нет: выбор скрыт, в запрос поле не попадает", async () => {
    const user = await openForm();
    await user.type(screen.getByRole("textbox", { name: "Название" }), "Видео");
    await next(user);
    await next(user);
    await user.selectOptions(screen.getByLabelText("Записать в досье, поле 1"), "phone");
    await user.click(screen.getByRole("radio", { name: /Ответ по группе/ }));
    expect(screen.queryByLabelText(/Записать в досье/)).not.toBeInTheDocument();
    await next(user);
    await user.click(screen.getByRole("button", { name: "Создать и разослать" }));
    expect(created()![1].fields).toEqual([expect.not.objectContaining({ dossier_field: expect.anything() })]);
  });

  it("шаблон заполняет форму целиком, кроме срока", async () => {
    templates = [TEMPLATE];
    const user = await openForm();
    await user.click(screen.getByRole("button", { name: /^Ежегодная сверка/ }));
    expect(screen.getByRole("textbox", { name: "Название" })).toHaveValue("Сверка контактов");
    expect(screen.getByRole("textbox", { name: "Что нужно сделать и как" })).toHaveValue("Проверить телефоны");
    await next(user);
    expect(screen.getByRole("radio", { name: /Курсы/ })).toBeChecked();
    expect(screen.getByLabelText(/1 курс/)).toBeChecked();
    expect(screen.getByLabelText(/3 курс/)).not.toBeChecked();
    await next(user);
    expect(screen.getByRole("radio", { name: /По выбранным студентам/ })).toBeChecked();
    expect(screen.getByDisplayValue("Спорт, Танцы")).toBeInTheDocument();
    expect(screen.getByLabelText("Записать в досье, поле 1")).toHaveValue("phone");
    await next(user);
    expect(screen.getByRole("radio", { name: REVIEWER_LABELS.two_step })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Создать и разослать" }));
    expect(created()![1]).toMatchObject({
      title: "Сверка контактов", collect_mode: "selected", reviewer_rule: "two_step",
      scope: { all_groups: false, department_ids: [], courses: [1, 2], group_ids: [], exclude_group_ids: [5] },
    });
  });

  it("без шаблонов галереи нет", async () => {
    templates = [];
    await openForm();
    expect(screen.queryByRole("group", { name: "Начать с шаблона" })).not.toBeInTheDocument();
  });

  it("удаление шаблона: подтверждение, запрос, шаблон исчезает", async () => {
    templates = [TEMPLATE];
    const user = await openForm();
    const confirm = vi.spyOn(dialogs, "confirm").mockResolvedValueOnce(false);
    await user.click(screen.getByRole("button", { name: "Удалить шаблон «Ежегодная сверка»" }));
    expect(confirm).toHaveBeenCalled();
    expect(del).not.toHaveBeenCalled();
    confirm.mockResolvedValueOnce(true);
    del.mockResolvedValue(undefined);
    await user.click(screen.getByRole("button", { name: "Удалить шаблон «Ежегодная сверка»" }));
    expect(del).toHaveBeenCalledWith("/tasks/templates/4");
    await waitFor(() => expect(screen.queryByRole("button", { name: /^Ежегодная сверка/ })).not.toBeInTheDocument());
  });

  it("чужой шаблон удалить нельзя", async () => {
    templates = [{ ...TEMPLATE, can_manage: false }];
    await openForm();
    expect(screen.getByRole("button", { name: /^Ежегодная сверка/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Удалить шаблон/ })).not.toBeInTheDocument();
  });

  it("вкладка «Шаблоны» показывает шаблоны и их расписание", async () => {
    templates = [{ ...TEMPLATE, repeat: "monthly", repeat_day: 1, due_offset_days: 14, next_run: "2026-11-01", last_run_date: null, last_error: null }];
    const user = userEvent.setup();
    mockApi();
    renderPage(<TasksPage />, { role: "admin" });
    await user.click(await screen.findByRole("button", { name: "Шаблоны" }));
    expect(await screen.findByText("Ежегодная сверка")).toBeInTheDocument();
    expect(screen.getByText(/Каждый месяц, 1-го числа/)).toBeInTheDocument();
    expect(screen.getByText("01.11.2026")).toBeInTheDocument();
  });

  it("следующий шаг: охват не спрашивается, выбирается момент открытия; уходит after_task_id", async () => {
    const user = userEvent.setup();
    mockApi({ detail: { ...DETAIL, steps: [], unlock_on: null } });
    post.mockResolvedValue({ ...DETAIL, id: 2 });
    renderPage(<TasksPage />, { role: "admin", route: "/tasks?task=1", path: "/tasks" });
    await screen.findByRole("heading", { name: "Кружки доп. образования" });
    await user.click(screen.getByText("Ещё"));
    await user.click(screen.getByRole("button", { name: "Добавить следующий шаг" }));
    expect(await screen.findByText("Следующий шаг после «Кружки доп. образования»")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Начать с шаблона" })).not.toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "Название" }), "Видео");
    await next(user);
    expect(screen.getByText(/те же группы, что у предыдущего шага/)).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /Весь колледж/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /Сразу после сдачи предыдущего/ }));
    await next(user);
    await user.type(screen.getByRole("textbox", { name: "Название поля 1" }), "Ссылка");
    await next(user);
    await user.click(screen.getByRole("button", { name: "Создать и разослать" }));
    expect(post).toHaveBeenCalledWith("/tasks", expect.objectContaining({ title: "Видео", after_task_id: 1, unlock_on: "submitted" }));
    expect(post).not.toHaveBeenCalledWith("/tasks/scope-preview", expect.anything());
  });

  it("после создания открывается карточка задачи", async () => {
    const user = await openForm();
    await user.type(screen.getByRole("textbox", { name: "Название" }), "Опрос");
    await next(user);
    await next(user);
    await user.type(screen.getByRole("textbox", { name: "Название поля 1" }), "Ответ");
    await next(user);
    await user.click(screen.getByRole("button", { name: "Создать и разослать" }));
    expect(await screen.findByRole("heading", { name: "Кружки доп. образования" })).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/tasks/1");
  });
});
