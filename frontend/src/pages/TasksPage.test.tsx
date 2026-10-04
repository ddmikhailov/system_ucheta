import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, downloadFile } from "../api/client";
import type { TaskDetail, TaskListRow } from "../api/types";
import { renderPage } from "../test/utils";
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
  { id: 1, title: "Кружки доп. образования", collect_mode: "student", reviewer_rule: "dept_head", due_date: "2026-10-06", is_closed: false, author_name: "Админ А.", progress },
  { id: 2, title: "Видеовизитка", collect_mode: "group", reviewer_rule: "two_step", due_date: "2026-10-14", is_closed: true, author_name: "Админ А.", progress: { ...progress, overdue: 0 } },
];

const DETAIL: TaskDetail = {
  id: 1, title: "Кружки доп. образования", description: "Собрать кружки", collect_mode: "student", reviewer_rule: "dept_head",
  due_date: "2026-10-06", is_closed: false, author_id: 1, author_name: "Админ А.",
  fields: [{ key: "f1", label: "Телефон", type: "text", required: true, options: [] }],
  scope: { all_groups: true, department_ids: [], courses: [], group_ids: [], exclude_group_ids: [] },
  can_manage: true, progress,
  assignments: [
    { id: 10, study_group_id: 1, group_code: "СА172", course: 1, department_name: "Диджитал", status: "submitted", is_overdue: false, submitted_at: "2026-10-01T09:00:00", reviewed_at: null },
    { id: 11, study_group_id: 2, group_code: "ИИ112", course: 1, department_name: "Диджитал", status: "new", is_overdue: true, submitted_at: null, reviewed_at: null },
    { id: 12, study_group_id: 3, group_code: "ИТ201", course: 2, department_name: "Диджитал", status: "accepted", is_overdue: false, submitted_at: null, reviewed_at: null },
  ],
};

function mockApi(over: { list?: TaskListRow[]; queue?: object[]; detail?: TaskDetail } = {}) {
  get.mockImplementation(async (path: string) => {
    if (path === "/tasks") return over.list ?? LIST;
    if (path === "/tasks/review-queue") return over.queue ?? [];
    if (path.startsWith("/tasks/")) return over.detail ?? DETAIL;
    if (path === "/admin/departments") return [{ id: 1, name: "Диджитал", is_active: true }, { id: 2, name: "Моссовет", is_active: true }];
    if (path === "/admin/groups") return [{ id: 1, code: "СА172", course: 1, is_active: true }, { id: 2, code: "ИИ112", course: 1, is_active: true }];
    throw new Error(`неожиданный запрос ${path}`);
  });
}

beforeEach(() => {
  for (const fn of [get, post, patch, del, download]) fn.mockReset();
  download.mockResolvedValue(undefined);
});

describe("TasksPage — список и очередь", () => {
  it("показывает задачи с прогрессом, просрочкой и меткой «закрыта»", async () => {
    mockApi();
    renderPage(<TasksPage />, { role: "admin" });
    expect(await screen.findByText("Кружки доп. образования")).toBeInTheDocument();
    const first = screen.getByText("Кружки доп. образования").closest("tr") as HTMLElement;
    expect(within(first).getByText(/сдано 4\/46, принято 1/)).toBeInTheDocument();
    expect(within(first).getByText("просрочено 2")).toBeInTheDocument();
    expect(within(first).getByText("06.10.2026")).toBeInTheDocument();
    const second = screen.getByText("Видеовизитка").closest("tr") as HTMLElement;
    expect(within(second).getByText("закрыта")).toBeInTheDocument();
    expect(within(second).queryByText(/просрочено/)).not.toBeInTheDocument();
  });

  it("пустой список подсказывает создать задачу", async () => {
    mockApi({ list: [] });
    renderPage(<TasksPage />, { role: "admin" });
    expect(await screen.findByText(/Задач пока нет/)).toBeInTheDocument();
  });

  it("счётчик на вкладке «На проверке» и список очереди со ссылкой на задачу", async () => {
    const user = userEvent.setup();
    mockApi({ queue: [{ id: 10, task_id: 1, title: "Кружки доп. образования", group_code: "СА172", department_name: "Диджитал", due_date: "2026-10-06", submitted_at: "2026-10-01T09:00:00", is_overdue: false }] });
    renderPage(<TasksPage />, { role: "dept_head" });
    const tab = await screen.findByRole("button", { name: "На проверке (1)" });
    await user.click(tab);
    const link = await screen.findByRole("link", { name: "Кружки доп. образования" });
    expect(link).toHaveAttribute("href", "/tasks/assignment/10");
    expect(screen.getByText(/01\.10\.2026/)).toBeInTheDocument();
  });

  it("пустая очередь проверки", async () => {
    const user = userEvent.setup();
    mockApi();
    renderPage(<TasksPage />, { role: "dept_head" });
    await user.click(await screen.findByRole("button", { name: "На проверке" }));
    expect(await screen.findByText("Ничего не ждёт вашей проверки.")).toBeInTheDocument();
  });

  it("ошибка загрузки списка показывается", async () => {
    get.mockRejectedValue(new ApiError(500, "Сервер недоступен"));
    renderPage(<TasksPage />, { role: "admin" });
    expect(await screen.findByText("Сервер недоступен")).toBeInTheDocument();
  });
});

describe("TasksPage — карточка задачи", () => {
  const openTask = () => renderPage(<TasksPage />, { route: "/tasks?task=1", role: "admin" });

  it("показывает форму, прогресс и группы со ссылками на назначения", async () => {
    mockApi();
    openTask();
    expect(await screen.findByRole("heading", { name: "Кружки доп. образования" })).toBeInTheDocument();
    expect(screen.getByText("Поля формы:").closest("p")).toHaveTextContent("Телефон *");
    expect(screen.getByRole("link", { name: "СА172" })).toHaveAttribute("href", "/tasks/assignment/10");
    expect(within(screen.getByRole("link", { name: "СА172" }).closest("tr") as HTMLElement).getByText("На проверке")).toBeInTheDocument();
    const overdue = screen.getByRole("link", { name: "ИИ112" }).closest("tr") as HTMLElement;
    expect(overdue).toHaveTextContent("просрочено");
  });

  it("фильтрует группы по статусу и по просрочке", async () => {
    const user = userEvent.setup();
    mockApi();
    openTask();
    await screen.findByRole("link", { name: "СА172" });
    await user.selectOptions(screen.getByRole("combobox"), "accepted");
    expect(screen.getByRole("link", { name: "ИТ201" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "СА172" })).not.toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox"), "overdue");
    expect(screen.getByRole("link", { name: "ИИ112" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "ИТ201" })).not.toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox"), "returned");
    expect(screen.getByText("Нет групп с таким статусом.")).toBeInTheDocument();
  });

  it("управление доступно только автору/админу: закрыть, удалить; выгрузка — всем", async () => {
    mockApi({ detail: { ...DETAIL, can_manage: false } });
    openTask();
    await screen.findByRole("heading", { name: "Кружки доп. образования" });
    expect(screen.getByRole("button", { name: "Выгрузить в Excel" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Закрыть задачу" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Удалить" })).not.toBeInTheDocument();
  });

  it("закрывает задачу и перезагружает карточку", async () => {
    const user = userEvent.setup();
    mockApi();
    patch.mockResolvedValue({});
    openTask();
    await user.click(await screen.findByRole("button", { name: "Закрыть задачу" }));
    expect(patch).toHaveBeenCalledWith("/tasks/1", { is_closed: true });
    await waitFor(() => expect(get.mock.calls.filter((c) => c[0] === "/tasks/1").length).toBeGreaterThanOrEqual(2));
  });

  it("удаление спрашивает подтверждение; ошибка сервера показывается", async () => {
    const user = userEvent.setup();
    mockApi();
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    openTask();
    await user.click(await screen.findByRole("button", { name: "Удалить" }));
    expect(del).not.toHaveBeenCalled();

    confirm.mockReturnValueOnce(true);
    del.mockRejectedValue(new ApiError(400, "По задаче уже есть ответы — закройте её вместо удаления"));
    await user.click(screen.getByRole("button", { name: "Удалить" }));
    expect(del).toHaveBeenCalledWith("/tasks/1");
    expect(await screen.findByText(/закройте её вместо удаления/)).toBeInTheDocument();
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

describe("TasksPage — создание задачи", () => {
  async function openForm(role = "admin") {
    const user = userEvent.setup();
    mockApi();
    renderPage(<TasksPage />, { role });
    await user.click(await screen.findByRole("button", { name: "+ Новая задача" }));
    return user;
  }

  it("отправляет охват, режим, проверяющего и форму ответа", async () => {
    const user = await openForm();
    post.mockResolvedValue(DETAIL);
    await user.type(screen.getByPlaceholderText("Название"), "Флюорография");
    await user.type(screen.getByPlaceholderText(/Описание/), "Справки у всех");
    await user.selectOptions(screen.getByDisplayValue("Весь колледж"), "courses");
    await user.click(await screen.findByLabelText(/1 курс/));
    await user.click(screen.getByLabelText(/2 курс/));
    await user.selectOptions(screen.getByDisplayValue("Зав. отделением группы"), "two_step");

    await user.type(screen.getByPlaceholderText("Название поля"), "Дата справки");
    await user.selectOptions(screen.getByDisplayValue("Текст"), "date");
    await user.click(screen.getByLabelText(/Обязательное/));
    await user.click(screen.getByRole("button", { name: "Создать и разослать" }));

    expect(post).toHaveBeenCalledTimes(1);
    const [path, body] = post.mock.calls[0] as [string, Record<string, unknown>];
    expect(path).toBe("/tasks");
    expect(body).toMatchObject({
      title: "Флюорография",
      description: "Справки у всех",
      collect_mode: "student",
      reviewer_rule: "two_step",
      fields: [{ label: "Дата справки", type: "date", required: true, options: [] }],
      scope: { all_groups: false, department_ids: [], courses: [1, 2], group_ids: [], exclude_group_ids: [] },
    });
  });

  it("поле выбора требует варианты и разбивает их по запятым", async () => {
    const user = await openForm();
    post.mockResolvedValue(DETAIL);
    await user.type(screen.getByPlaceholderText("Название"), "Кружки");
    await user.type(screen.getByPlaceholderText("Название поля"), "Что посещает");
    await user.selectOptions(screen.getByDisplayValue("Текст"), "multiselect");
    expect(screen.getByPlaceholderText("Варианты через запятую")).toBeRequired();
    await user.type(screen.getByPlaceholderText("Варианты через запятую"), "Спорт, Танцы ,, Шахматы");
    await user.click(screen.getByRole("button", { name: "Создать и разослать" }));
    expect(post.mock.calls[0][1]).toMatchObject({
      fields: [{ label: "Что посещает", type: "multiselect", options: ["Спорт", "Танцы", "Шахматы"] }],
    });
  });

  it("у зав. отделением нет выбора отделений, охват по умолчанию — своё отделение", async () => {
    await openForm("dept_head");
    expect(screen.getByDisplayValue("Всё моё отделение")).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Выбранные отделения" })).not.toBeInTheDocument();
  });

  it("поля формы можно добавлять, двигать и убирать (последнее убрать нельзя)", async () => {
    const user = await openForm();
    const removeButtons = () => screen.getAllByRole("button", { name: "Убрать" });
    expect(removeButtons()[0]).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "+ Добавить поле" }));
    const names = () => screen.getAllByPlaceholderText("Название поля") as HTMLInputElement[];
    await user.type(names()[0], "Первое");
    await user.type(names()[1], "Второе");
    await user.click(screen.getAllByRole("button", { name: "Ниже" })[0]);
    expect(names().map((n) => n.value)).toEqual(["Второе", "Первое"]);
    await user.click(removeButtons()[0]);
    expect(names().map((n) => n.value)).toEqual(["Первое"]);
    expect(removeButtons()[0]).toBeDisabled();
  });

  it("ошибка сервера показывается, введённое остаётся", async () => {
    const user = await openForm();
    post.mockRejectedValue(new ApiError(400, "В охват не попала ни одна группа"));
    await user.type(screen.getByPlaceholderText("Название"), "Опрос");
    await user.type(screen.getByPlaceholderText("Название поля"), "Ответ");
    await user.click(screen.getByRole("button", { name: "Создать и разослать" }));
    expect(await screen.findByText("В охват не попала ни одна группа")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Название")).toHaveValue("Опрос");
  });

  it("после создания открывается карточка задачи", async () => {
    const user = await openForm();
    post.mockResolvedValue({ ...DETAIL, id: 1 });
    await user.type(screen.getByPlaceholderText("Название"), "Опрос");
    await user.type(screen.getByPlaceholderText("Название поля"), "Ответ");
    await user.click(screen.getByRole("button", { name: "Создать и разослать" }));
    expect(await screen.findByRole("heading", { name: "Кружки доп. образования" })).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/tasks/1");
  });
});
