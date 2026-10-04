import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { AssignmentDetail } from "../api/types";
import { renderPage } from "../test/utils";
import TaskAssignmentPage from "./TaskAssignmentPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const FIELDS: AssignmentDetail["fields"] = [
  { key: "f1", label: "Кружки", type: "multiselect", required: false, options: ["Спорт", "Танцы"] },
  { key: "f2", label: "Не посещает", type: "bool", required: false, options: [] },
  { key: "f3", label: "Телефон родителя", type: "text", required: true, options: [] },
];

function detail(overrides: Partial<AssignmentDetail> = {}): AssignmentDetail {
  return {
    id: 5,
    task_id: 1,
    title: "Кружки доп. образования",
    description: "Собрать данные о кружках",
    collect_mode: "student",
    reviewer_rule: "dept_head",
    due_date: "2026-10-06",
    is_closed: false,
    fields: FIELDS,
    study_group_id: 7,
    group_code: "СА172",
    status: "new",
    is_overdue: false,
    group_values: {},
    rows: [
      { student_id: 11, student_name: "Алексеев Пётр", is_included: true, values: {} },
      { student_id: 12, student_name: "Андреева Елена", is_included: true, values: { f3: "+7 900" } },
    ],
    comments: [],
    review_comment: null,
    submitted_at: null,
    reviewed_at: null,
    reviewed_by_name: null,
    history: [],
    review_step: 1,
    review_steps: 1,
    can_edit: true,
    can_submit: true,
    can_review: false,
    ...overrides,
  };
}

const get = vi.mocked(api.get);
const put = vi.mocked(api.put);
const post = vi.mocked(api.post);

function open(d: AssignmentDetail, role = "curator") {
  get.mockResolvedValue(d);
  return renderPage(<TaskAssignmentPage />, { route: `/tasks/assignment/${d.id}`, path: "/tasks/assignment/:assignmentId", role });
}

beforeEach(() => {
  for (const fn of [get, put, post]) fn.mockReset();
});

describe("TaskAssignmentPage — связь с досье", () => {
  it("связанный столбец помечен «(досье)», подставленные из досье значения видны в строках", async () => {
    const fields = [
      { key: "f3", label: "Телефон", type: "text" as const, required: false, options: [], dossier_field: "phone" },
      { key: "f4", label: "Заметка", type: "text" as const, required: false, options: [] },
    ];
    open(detail({
      fields,
      rows: [{ student_id: 11, student_name: "Алексеев Пётр", is_included: true, values: { f3: "+7 900 111-22-33" } }],
    }));
    expect(await screen.findByRole("columnheader", { name: /Телефон.*\(досье\)/ })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Заметка" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("+7 900 111-22-33")).toBeInTheDocument();
  });
});

describe("TaskAssignmentPage — заполнение", () => {
  it("показывает задачу, срок, режим и студентов", async () => {
    open(detail());
    expect(await screen.findByRole("heading", { name: "Кружки доп. образования" })).toBeInTheDocument();
    expect(screen.getByText(/срок 06\.10\.2026/)).toBeInTheDocument();
    expect(screen.getByText(/По каждому студенту/)).toBeInTheDocument();
    expect(screen.getByText("Собрать данные о кружках")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Алексеев Пётр" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Андреева Елена" })).toBeInTheDocument();
    expect(screen.getByText("Не начато")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/tasks/assignments/5");
  });

  it("помечает просроченную задачу и возврат с комментарием проверяющего", async () => {
    open(detail({ is_overdue: true, status: "returned", review_comment: "У Иванова нет кружка" }));
    expect(await screen.findByText("просрочено")).toBeInTheDocument();
    expect(screen.getByText(/Возвращено на доработку: У Иванова нет кружка/)).toBeInTheDocument();
  });

  it("«Сохранить черновик» доступна только после правки и отправляет все строки", async () => {
    const user = userEvent.setup();
    open(detail());
    const save = await screen.findByRole("button", { name: "Сохранить черновик" });
    expect(save).toBeDisabled();

    const row = screen.getByRole("row", { name: /Алексеев Пётр/ });
    await user.type(within(row).getByRole("textbox"), "+7 911");
    await user.click(within(row).getByLabelText("Спорт"));
    expect(save).toBeEnabled();

    put.mockResolvedValue(detail({ status: "in_progress" }));
    await user.click(save);
    expect(put).toHaveBeenCalledWith("/tasks/assignments/5/answers", {
      group_values: {},
      rows: [
        { student_id: 11, is_included: true, values: { f3: "+7 911", f1: ["Спорт"] } },
        { student_id: 12, is_included: true, values: { f3: "+7 900" } },
      ],
    });
    expect(await screen.findByText("Черновик сохранён")).toBeInTheDocument();
    expect(screen.getByText("В работе")).toBeInTheDocument();
  });

  it("снятая галочка множественного выбора убирает вариант", async () => {
    const user = userEvent.setup();
    open(detail({ rows: [{ student_id: 11, student_name: "Алексеев Пётр", is_included: true, values: { f1: ["Спорт", "Танцы"], f3: "1" } }] }));
    const row = await screen.findByRole("row", { name: /Алексеев Пётр/ });
    await user.click(within(row).getByLabelText("Танцы"));
    put.mockResolvedValue(detail());
    await user.click(screen.getByRole("button", { name: "Сохранить черновик" }));
    expect(put.mock.calls[0][1]).toMatchObject({ rows: [{ values: { f1: ["Спорт"] } }] });
  });

  it("отправка на проверку сначала сохраняет несохранённое, потом отправляет", async () => {
    const user = userEvent.setup();
    open(detail());
    const row = await screen.findByRole("row", { name: /Алексеев Пётр/ });
    await user.type(within(row).getByRole("textbox"), "+7 911");

    put.mockResolvedValue(detail());
    post.mockResolvedValue(detail({ status: "submitted", can_edit: false, can_submit: false }));
    await user.click(screen.getByRole("button", { name: "Отправить на проверку" }));

    await waitFor(() => expect(post).toHaveBeenCalledWith("/tasks/assignments/5/submit"));
    expect(put).toHaveBeenCalledTimes(1);
    expect(put.mock.invocationCallOrder[0]).toBeLessThan(post.mock.invocationCallOrder[0]);
    expect(await screen.findByText("Отправлено на проверку")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Отправить на проверку" })).not.toBeInTheDocument();
  });

  it("без правок отправка идёт без лишнего сохранения", async () => {
    const user = userEvent.setup();
    open(detail());
    post.mockResolvedValue(detail({ status: "submitted", can_edit: false, can_submit: false }));
    await user.click(await screen.findByRole("button", { name: "Отправить на проверку" }));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(put).not.toHaveBeenCalled();
  });

  it("если проверка не пускает — показывает причину и оставляет возможность править", async () => {
    const user = userEvent.setup();
    open(detail());
    post.mockRejectedValue(new ApiError(400, "Нельзя отправить: Алексеев Пётр: не заполнено — Телефон родителя"));
    await user.click(await screen.findByRole("button", { name: "Отправить на проверку" }));
    expect(await screen.findByText(/не заполнено — Телефон родителя/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Отправить на проверку" })).toBeEnabled();
    expect(window.scrollTo).toHaveBeenCalled(); // к ошибке прокручиваем, она вверху страницы
  });

  it("задача, принятая без проверки, сообщает об этом", async () => {
    const user = userEvent.setup();
    open(detail({ reviewer_rule: "none" }));
    post.mockResolvedValue(detail({ status: "accepted", can_edit: false, can_submit: false }));
    await user.click(await screen.findByRole("button", { name: "Отправить на проверку" }));
    expect(await screen.findByText("Задача принята")).toBeInTheDocument();
  });

  it("в режиме только чтения поля недоступны и кнопок нет", async () => {
    open(detail({ can_edit: false, can_submit: false, status: "submitted" }));
    const row = await screen.findByRole("row", { name: /Алексеев Пётр/ });
    expect(within(row).getByRole("textbox")).toBeDisabled();
    expect(within(row).getByLabelText("Спорт")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Сохранить черновик" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Отправить на проверку" })).not.toBeInTheDocument();
  });

  it("при двухступенчатой проверке показывает ступень", async () => {
    open(detail({ status: "submitted", review_steps: 2, review_step: 2, can_edit: false, can_submit: false }));
    expect(await screen.findByText(/На проверке \(ступень 2 из 2\)/)).toBeInTheDocument();
  });
});

describe("TaskAssignmentPage — режимы сбора", () => {
  const groupDetail = detail({
    collect_mode: "group",
    fields: [{ key: "f1", label: "Ссылка на видео", type: "link", required: true, options: [] }],
    rows: [],
  });

  it("групповой ответ: поле-ссылка и сохранение group_values без строк", async () => {
    const user = userEvent.setup();
    open(groupDetail);
    const input = await screen.findByPlaceholderText("https://…");
    expect(input).toHaveAttribute("type", "url");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();

    await user.type(input, "https://vk.com/video1");
    put.mockResolvedValue(groupDetail);
    await user.click(screen.getByRole("button", { name: "Сохранить черновик" }));
    expect(put).toHaveBeenCalledWith("/tasks/assignments/5/answers", {
      group_values: { f1: "https://vk.com/video1" },
      rows: [],
    });
  });

  it("«по выбранным»: поля студента скрыты, пока его не отметили", async () => {
    const user = userEvent.setup();
    open(detail({
      collect_mode: "selected",
      fields: [FIELDS[2]],
      rows: [{ student_id: 11, student_name: "Алексеев Пётр", is_included: false, values: {} }],
    }));
    const row = await screen.findByRole("row", { name: /Алексеев Пётр/ });
    expect(within(row).queryByRole("textbox")).not.toBeInTheDocument();
    await user.click(within(row).getByRole("checkbox"));
    expect(within(row).getByRole("textbox")).toBeInTheDocument();

    put.mockResolvedValue(detail());
    await user.type(within(row).getByRole("textbox"), "тема");
    await user.click(screen.getByRole("button", { name: "Сохранить черновик" }));
    expect(put.mock.calls[0][1]).toEqual({
      group_values: {},
      rows: [{ student_id: 11, is_included: true, values: { f3: "тема" } }],
    });
  });
});

describe("TaskAssignmentPage — проверка и комментарии", () => {
  it("проверяющий видит панель; «Принять» отправляется без комментария", async () => {
    const user = userEvent.setup();
    open(detail({ status: "submitted", can_edit: false, can_submit: false, can_review: true }), "dept_head");
    post.mockResolvedValue(detail({ status: "accepted", can_review: false, can_edit: false }));
    await user.click(await screen.findByRole("button", { name: "Принять" }));
    expect(post).toHaveBeenCalledWith("/tasks/assignments/5/review", { action: "accept", comment: null });
    // «Принято» — и в статусе, и в уведомлении об операции.
    expect(await screen.findAllByText("Принято")).toHaveLength(2);
  });

  it("возврат уходит с комментарием", async () => {
    const user = userEvent.setup();
    open(detail({ status: "submitted", can_edit: false, can_submit: false, can_review: true }), "dept_head");
    await user.type(await screen.findByPlaceholderText(/Комментарий \(обязателен/), "Допишите телефоны");
    post.mockResolvedValue(detail({ status: "returned" }));
    await user.click(screen.getByRole("button", { name: "Вернуть на доработку" }));
    expect(post).toHaveBeenCalledWith("/tasks/assignments/5/review", { action: "return", comment: "Допишите телефоны" });
    expect(await screen.findByText("Возвращено на доработку")).toBeInTheDocument();
  });

  it("без права проверки панели нет", async () => {
    open(detail({ status: "submitted", can_edit: false, can_submit: false, can_review: false }));
    await screen.findByRole("heading", { name: "Кружки доп. образования" });
    expect(screen.queryByRole("button", { name: "Принять" })).not.toBeInTheDocument();
  });

  it("комментарий к студенту уходит с student_id, а ко всему ответу — с null", async () => {
    const user = userEvent.setup();
    open(detail({ comments: [{ id: 1, student_id: 11, author_name: "Зав. отд.", text: "Проверьте телефон", created_at: "2026-10-01T09:00:00" }] }));
    expect(await screen.findByText(/Проверьте телефон/)).toBeInTheDocument();
    expect(screen.getByText(/Алексеев Пётр/, { selector: "li" })).toBeInTheDocument(); // комментарий подписан студентом

    post.mockResolvedValue({});
    await user.selectOptions(screen.getByLabelText("К кому комментарий"), "12");
    await user.type(screen.getByPlaceholderText("Написать комментарий"), "Уточните");
    await user.click(screen.getByRole("button", { name: "Отправить" }));
    expect(post).toHaveBeenCalledWith("/tasks/assignments/5/comments", { text: "Уточните", student_id: 12 });

    await waitFor(() => expect(screen.getByLabelText("К кому комментарий")).toHaveValue(""));
    await user.type(screen.getByPlaceholderText("Написать комментарий"), "Общее");
    await user.click(screen.getByRole("button", { name: "Отправить" }));
    expect(post).toHaveBeenLastCalledWith("/tasks/assignments/5/comments", { text: "Общее", student_id: null });
  });

  it("у группового ответа нет выбора студента для комментария", async () => {
    open(detail({ collect_mode: "group", rows: [], fields: [{ key: "f1", label: "Сдано", type: "bool", required: false, options: [] }] }));
    await screen.findByRole("heading", { name: "Кружки доп. образования" });
    expect(screen.queryByLabelText("К кому комментарий")).not.toBeInTheDocument();
  });

  it("если задачу не загрузить, показывает ошибку сервера", async () => {
    get.mockRejectedValue(new ApiError(403, "Нет доступа к этой задаче"));
    renderPage(<TaskAssignmentPage />, { route: "/tasks/assignment/5", path: "/tasks/assignment/:assignmentId" });
    expect(await screen.findByText("Нет доступа к этой задаче")).toBeInTheDocument();
  });
});


describe("TaskAssignmentPage — ход проверки", () => {
  it("показывает, кто и когда отправил, вернул и принял, с номером ступени", async () => {
    open(detail({
      status: "accepted", can_edit: false, can_submit: false, review_steps: 2, review_step: 1,
      reviewed_at: "2026-10-03T12:30:00", reviewed_by_name: "Петрова Н.",
      history: [
        { kind: "submitted", user_name: "Иванова А.", at: "2026-10-01T09:00:00", step: null },
        { kind: "returned", user_name: "Сидоров С.", at: "2026-10-01T10:00:00", step: 1 },
        { kind: "accepted", user_name: "Сидоров С.", at: "2026-10-02T11:00:00", step: 1 },
        { kind: "accepted", user_name: "Петрова Н.", at: "2026-10-03T12:30:00", step: 2 },
      ],
    }));
    expect(await screen.findByRole("heading", { name: "Ход проверки" })).toBeInTheDocument();
    const items = screen.getAllByRole("listitem").filter((li) => /Отправлено|Принято|Возвращено/.test(li.textContent ?? ""));
    expect(items.map((li) => li.textContent)).toEqual([
      expect.stringMatching(/Отправлено на проверку · Иванова А\./),
      expect.stringMatching(/Возвращено на доработку \(ступень 1 из 2\) · Сидоров С\./),
      expect.stringMatching(/Принято \(ступень 1 из 2\) · Сидоров С\./),
      expect.stringMatching(/Принято \(ступень 2 из 2\) · Петрова Н\./),
    ]);
    expect(screen.getByText(/проверил\(а\): Петрова Н\./)).toBeInTheDocument();
  });

  it("принятое без проверки помечено как автоматическое", async () => {
    open(detail({
      status: "accepted", can_edit: false, can_submit: false, reviewed_at: "2026-10-03T12:30:00", reviewed_by_name: null,
      history: [
        { kind: "submitted", user_name: "Иванова А.", at: "2026-10-03T12:30:00", step: null },
        { kind: "auto_accepted", user_name: null, at: "2026-10-03T12:30:00", step: null },
      ],
    }));
    expect(await screen.findByText(/Принято автоматически/)).toBeInTheDocument();
    expect(screen.getByText(/без проверки/)).toBeInTheDocument();
  });

  it("пока истории нет — раздела нет, а «Принято…» не показывается у неотправленной", async () => {
    open(detail());
    await screen.findByRole("heading", { name: "Кружки доп. образования" });
    expect(screen.queryByRole("heading", { name: "Ход проверки" })).not.toBeInTheDocument();
    expect(screen.queryByText(/проверил\(а\)/)).not.toBeInTheDocument();
  });
});
