import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
    due_date: "2026-10-09",
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
    is_locked: false,
    locked_reason: null,
    step_no: 1,
    step_total: null,
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

function setup() {
  return userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
}

/** Дождаться автосохранения (пауза 1,5 с после последней правки). */
async function autosave() {
  await act(() => vi.advanceTimersByTimeAsync(1600));
}

// Имя студента встречается и в списке «К кому комментарий» — ищем именно строку ответа.
const NAME = { selector: ".answer-row__name" };

function row(name: string) {
  return screen.getByText(name, NAME).closest(".answer-row") as HTMLElement;
}

beforeEach(() => {
  for (const fn of [get, put, post]) fn.mockReset();
  put.mockResolvedValue(detail({ status: "in_progress" }));
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date(2026, 9, 4, 10, 0));
});

afterEach(() => vi.useRealTimers());

describe("TaskAssignmentPage — шапка", () => {
  it("название, группа, срок словами, статус, режим, проверяющий и кольцо заполненности", async () => {
    open(detail());
    expect(await screen.findByRole("heading", { name: "Кружки доп. образования" })).toBeInTheDocument();
    expect(screen.getByText("СА172")).toBeInTheDocument();
    expect(screen.getByText("срок пт 09.10, через 5 дней")).toBeInTheDocument();
    expect(screen.getByText("Не начато")).toBeInTheDocument();
    expect(screen.getByText("По каждому студенту")).toBeInTheDocument();
    expect(screen.getByText(/проверяет: Зав\. отделением группы/)).toBeInTheDocument();
    expect(screen.getByText("Собрать данные о кружках")).toBeInTheDocument();
    // У Андреевой обязательный телефон есть — она заполнена, Алексеев — нет.
    expect(screen.getByRole("img", { name: "Заполнено 1 из 2" })).toBeInTheDocument();
  });

  it("возврат — заметное замечание проверяющего; просрочка — в статусе", async () => {
    open(detail({ status: "returned", review_comment: "Нет телефона у Алексеева" }));
    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent("Вернули на доработку");
    expect(note).toHaveTextContent("Нет телефона у Алексеева");

    open(detail({ status: "in_progress", is_overdue: true, due_date: "2026-10-02" }));
    expect(await screen.findByText("В работе, просрочено")).toBeInTheDocument();
  });

  it("двухступенчатая проверка: ступень в статусе", async () => {
    open(detail({ status: "submitted", review_step: 2, review_steps: 2, can_edit: false, can_submit: false }));
    expect(await screen.findByText("На проверке (ступень 2 из 2)")).toBeInTheDocument();
  });

  it("закрытый шаг: пояснение и никаких полей ввода", async () => {
    open(detail({ is_locked: true, locked_reason: "Откроется, когда примут шаг 1", can_edit: false, can_submit: false, step_no: 2, step_total: 2 }));
    expect(await screen.findByText("Откроется, когда примут шаг 1")).toBeInTheDocument();
    expect(screen.getByText("шаг 2 из 2")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /Телефон родителя/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Отправить на проверку" })).not.toBeInTheDocument();
  });

  it("ошибка загрузки — текст сервера", async () => {
    get.mockRejectedValue(new ApiError(404, "Задача не найдена"));
    renderPage(<TaskAssignmentPage />, { route: "/tasks/assignment/9", path: "/tasks/assignment/:assignmentId", role: "curator" });
    expect(await screen.findByText("Задача не найдена")).toBeInTheDocument();
  });
});

describe("TaskAssignmentPage — заполнение и автосохранение", () => {
  it("чипы и «да/нет» переключаются касанием, повторное касание снимает выбор", async () => {
    const user = setup();
    open(detail());
    await screen.findByText("Алексеев Пётр", NAME);
    const circles = screen.getByRole("group", { name: "Кружки: Алексеев Пётр" });
    const sport = within(circles).getByRole("button", { name: "Спорт" });
    await user.click(sport);
    expect(sport).toHaveAttribute("aria-pressed", "true");
    await user.click(within(circles).getByRole("button", { name: "Танцы" }));
    await user.click(sport);
    expect(sport).toHaveAttribute("aria-pressed", "false");

    const yesNo = screen.getByRole("group", { name: "Не посещает: Алексеев Пётр" });
    await user.click(within(yesNo).getByRole("button", { name: "Да" }));
    expect(within(yesNo).getByRole("button", { name: "Да" })).toHaveAttribute("aria-pressed", "true");
    await user.click(within(yesNo).getByRole("button", { name: "Да" }));
    expect(within(yesNo).getByRole("button", { name: "Да" })).toHaveAttribute("aria-pressed", "false");
  });

  it("сохраняет сам через паузу одним запросом со всеми строками и пишет время", async () => {
    const user = setup();
    open(detail());
    await screen.findByText("Алексеев Пётр", NAME);
    put.mockResolvedValue(detail({ status: "in_progress" }));
    await user.click(within(screen.getByRole("group", { name: "Кружки: Алексеев Пётр" })).getByRole("button", { name: "Спорт" }));
    await user.type(screen.getByRole("textbox", { name: "Телефон родителя: Алексеев Пётр" }), "+7 901");
    expect(screen.getByText("Есть несохранённые правки")).toBeInTheDocument();
    expect(put).not.toHaveBeenCalled();

    await autosave();
    expect(put).toHaveBeenCalledTimes(1);
    expect(put).toHaveBeenCalledWith("/tasks/assignments/5/answers", {
      group_values: {},
      rows: [
        { student_id: 11, is_included: true, values: { f1: ["Спорт"], f3: "+7 901" } },
        { student_id: 12, is_included: true, values: { f3: "+7 900" } },
      ],
    });
    expect(await screen.findByText("Сохранено в 10:00")).toBeInTheDocument();
    expect(screen.getByText("В работе")).toBeInTheDocument();
  });

  it("ошибка сохранения видна в панели и не теряет правки", async () => {
    const user = setup();
    open(detail());
    await screen.findByText("Алексеев Пётр", NAME);
    put.mockRejectedValue(new ApiError(400, "«Телефон родителя»: слишком длинный текст"));
    await user.type(screen.getByRole("textbox", { name: "Телефон родителя: Алексеев Пётр" }), "1");
    await autosave();
    expect(await screen.findByText("Не сохранено: «Телефон родителя»: слишком длинный текст")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Телефон родителя: Алексеев Пётр" })).toHaveValue("1");
  });

  it("неверная ссылка не уходит на сервер, пока её не допишут", async () => {
    const user = setup();
    const fields: AssignmentDetail["fields"] = [{ key: "v", label: "Видео", type: "link", required: true, options: [] }];
    open(detail({ collect_mode: "group", fields, rows: [] }));
    const input = await screen.findByRole("textbox", { name: "Видео" });
    await user.type(input, "vk.com");
    await autosave();
    expect(put).not.toHaveBeenCalled();
    expect(screen.getByText("Не сохранено: «Видео»: нужна ссылка вида https://…")).toBeInTheDocument();
    expect(input).toHaveAttribute("aria-invalid", "true");

    put.mockResolvedValue(detail({ collect_mode: "group", fields, rows: [], group_values: { v: "https://vk.com/v1" } }));
    await user.clear(input);
    await user.type(input, "https://vk.com/v1");
    await autosave();
    expect(put).toHaveBeenCalledWith("/tasks/assignments/5/answers", { group_values: { v: "https://vk.com/v1" }, rows: [] });
  });

  it("отправка держится, пока пусты обязательные поля, и объясняет почему", async () => {
    open(detail());
    expect(await screen.findByText("Обязательные поля пусты у 1 студента")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Отправить на проверку" })).toBeDisabled();
  });

  it("отправка сначала дописывает черновик, потом отправляет", async () => {
    const user = setup();
    open(detail());
    await screen.findByText("Алексеев Пётр", NAME);
    put.mockResolvedValue(detail({ status: "in_progress", rows: detail().rows.map((r) => ({ ...r, values: { f3: "+7" } })) }));
    post.mockResolvedValue(detail({ status: "submitted", can_edit: false, can_submit: false }));
    await user.type(screen.getByRole("textbox", { name: "Телефон родителя: Алексеев Пётр" }), "+7");
    await user.click(screen.getByRole("button", { name: "Отправить на проверку" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/tasks/assignments/5/submit"));
    expect(put.mock.invocationCallOrder[0]).toBeLessThan(post.mock.invocationCallOrder[0]);
    expect(await screen.findByText("На проверке")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Отправить на проверку" })).not.toBeInTheDocument();
  });

  it("отказ сервера при отправке показывается, правка остаётся доступной", async () => {
    const user = setup();
    open(detail({ rows: [{ student_id: 12, student_name: "Андреева Елена", is_included: true, values: { f3: "+7 900" } }] }));
    post.mockRejectedValue(new ApiError(400, "Нельзя отправить: срок закрыт"));
    await user.click(await screen.findByRole("button", { name: "Отправить на проверку" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Нельзя отправить: срок закрыт");
    expect(screen.getByRole("textbox", { name: "Телефон родителя: Андреева Елена" })).toBeEnabled();
  });

  it("без проверки кнопка называется «Отправить»", async () => {
    open(detail({ reviewer_rule: "none", rows: [{ student_id: 12, student_name: "Андреева Елена", is_included: true, values: { f3: "+7" } }] }));
    expect(await screen.findByRole("button", { name: "Отправить" })).toBeEnabled();
    expect(screen.getByText("Заполнено: 1 из 1")).toBeInTheDocument();
  });

  it("фильтр «Не заполнены» оставляет только тех, кого осталось заполнить", async () => {
    const user = setup();
    open(detail());
    await screen.findByText("Алексеев Пётр", NAME);
    await user.click(screen.getByRole("button", { name: "Не заполнены 1" }));
    expect(screen.getByText("Алексеев Пётр", NAME)).toBeInTheDocument();
    expect(screen.queryByText("Андреева Елена", NAME)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Все 2" }));
    expect(screen.getByText("Андреева Елена", NAME)).toBeInTheDocument();
  });

  it("«Заполнить столбец» ставит значение пустым строкам, а с галочкой — всем", async () => {
    const user = setup();
    open(detail({ rows: [...detail().rows, { student_id: 13, student_name: "Волкова Анна", is_included: true, values: { f2: false } }] }));
    await screen.findByText("Волкова Анна", NAME);
    await user.click(screen.getByRole("button", { name: "Заполнить столбец" }));
    const panel = screen.getByRole("group", { name: "Заполнить столбец" });
    await user.selectOptions(within(panel).getByRole("combobox"), "f2");
    await user.click(within(within(panel).getByRole("group", { name: "Значение для всех: Не посещает" })).getByRole("button", { name: "Да" }));
    await user.click(within(panel).getByRole("button", { name: "Заполнить 2 студентам" }));
    expect(within(screen.getByRole("group", { name: "Не посещает: Алексеев Пётр" })).getByRole("button", { name: "Да" })).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByRole("group", { name: "Не посещает: Волкова Анна" })).getByRole("button", { name: "Нет" })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "Заполнить столбец" }));
    const again = screen.getByRole("group", { name: "Заполнить столбец" });
    await user.selectOptions(within(again).getByRole("combobox"), "f2");
    await user.click(within(within(again).getByRole("group", { name: "Значение для всех: Не посещает" })).getByRole("button", { name: "Нет" }));
    await user.click(within(again).getByRole("checkbox", { name: /Заменить и уже заполненные/ }));
    await user.click(within(again).getByRole("button", { name: "Заполнить 3 студентам" }));
    expect(within(screen.getByRole("group", { name: "Не посещает: Алексеев Пётр" })).getByRole("button", { name: "Нет" })).toHaveAttribute("aria-pressed", "true");
  });

  it("подставленное из досье помечено, пока строку не тронули", async () => {
    const user = setup();
    open(detail({ rows: [{ student_id: 11, student_name: "Алексеев Пётр", is_included: true, values: { f3: "+7 900" }, from_dossier: true }] }));
    expect(await screen.findByText("из досье, проверьте")).toBeInTheDocument();
    await user.click(within(screen.getByRole("group", { name: "Кружки: Алексеев Пётр" })).getByRole("button", { name: "Спорт" }));
    expect(screen.queryByText("из досье, проверьте")).not.toBeInTheDocument();
  });

  it("«по выбранным»: поля появляются, когда студента отметили", async () => {
    const user = setup();
    open(detail({ collect_mode: "selected", rows: detail().rows.map((r) => ({ ...r, is_included: false, values: {} })) }));
    await screen.findByText("Алексеев Пётр", NAME);
    expect(screen.queryByRole("textbox", { name: "Телефон родителя: Алексеев Пётр" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Отправить на проверку" })).toBeEnabled();
    await user.click(within(row("Алексеев Пётр")).getByRole("checkbox", { name: /касается/ }));
    expect(screen.getByRole("textbox", { name: "Телефон родителя: Алексеев Пётр" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Заполнено 0 из 1" })).toBeInTheDocument();
  });

  it("никого не отметили в «по выбранным» — отправить можно (задача никого не касается)", async () => {
    open(detail({ collect_mode: "selected", rows: detail().rows.map((r) => ({ ...r, is_included: false, values: {} })) }));
    expect(await screen.findByRole("button", { name: "Отправить на проверку" })).toBeEnabled();
  });

  it("только чтение: значения текстом, панели отправки нет", async () => {
    open(detail({ status: "submitted", can_edit: false, can_submit: false, rows: [{ student_id: 11, student_name: "Алексеев Пётр", is_included: true, values: { f1: ["Спорт", "Танцы"], f2: true, f3: "+7" } }] }));
    expect(await screen.findByText("Спорт, Танцы")).toBeInTheDocument();
    expect(screen.getByText("да")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Отправить на проверку" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Заполнить столбец" })).not.toBeInTheDocument();
  });

  it("принятое: кто и когда принял", async () => {
    open(detail({ status: "accepted", can_edit: false, can_submit: false, reviewed_at: "2026-10-03T09:15:00", reviewed_by_name: "Зав. Отделением" }));
    expect(await screen.findByText(/Принято 03\.10\.2026.*проверил\(а\): Зав\. Отделением/)).toBeInTheDocument();
  });
});

describe("TaskAssignmentPage — проверка", () => {
  const forReview = () => detail({ status: "submitted", can_edit: false, can_submit: false, can_review: true });

  it("«Принять» уходит без комментария", async () => {
    const user = setup();
    open(forReview(), "dept_head");
    post.mockResolvedValue(detail({ status: "accepted", can_edit: false, can_submit: false }));
    await user.click(await screen.findByRole("button", { name: "Принять" }));
    expect(post).toHaveBeenCalledWith("/tasks/assignments/5/review", { action: "accept", comment: null });
    expect(await screen.findByText("Принято")).toBeInTheDocument();
  });

  it("вернуть без комментария нельзя; с комментарием — уходит", async () => {
    const user = setup();
    open(forReview(), "dept_head");
    await user.click(await screen.findByRole("button", { name: "Вернуть на доработку" }));
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("без комментария вернуть нельзя");
    post.mockResolvedValue(detail({ status: "returned", review_comment: "Нет телефона", can_edit: false, can_submit: false }));
    await user.type(screen.getByRole("textbox", { name: "Комментарий проверяющего" }), "Нет телефона");
    await user.click(screen.getByRole("button", { name: "Вернуть на доработку" }));
    expect(post).toHaveBeenCalledWith("/tasks/assignments/5/review", { action: "return", comment: "Нет телефона" });
  });

  it("без права проверки панели нет", async () => {
    open(detail());
    await screen.findByText("Алексеев Пётр", NAME);
    expect(screen.queryByRole("region", { name: "Проверка" })).not.toBeInTheDocument();
  });
});

describe("TaskAssignmentPage — обсуждение", () => {
  it("ход проверки и комментарии — одной лентой по времени", async () => {
    open(
      detail({
        status: "returned",
        review_steps: 2,
        history: [
          { kind: "submitted", user_name: "Иванова А. И.", at: "2026-10-01T08:00:00", step: null },
          { kind: "returned", user_name: "Зав. Отделением", at: "2026-10-02T09:00:00", step: 1 },
        ],
        comments: [{ id: 1, student_id: null, author_name: "Зав. Отделением", text: "Проверьте телефоны", created_at: "2026-10-01T12:00:00" }],
      })
    );
    const thread = await screen.findByRole("region", { name: "Обсуждение" });
    const items = within(thread).getAllByRole("listitem").map((li) => li.textContent);
    expect(items[0]).toContain("Отправлено на проверку");
    expect(items[1]).toContain("Проверьте телефоны");
    expect(items[2]).toContain("Возвращено на доработку (ступень 1 из 2)");
    expect(items[2]).toContain("Зав. Отделением");
  });

  it("замечание к студенту видно в его строке и даёт фильтр", async () => {
    const user = setup();
    open(detail({ comments: [{ id: 1, student_id: 12, author_name: "Зав.", text: "Уточните телефон", created_at: "2026-10-01T12:00:00" }] }));
    expect(await screen.findByText("Замечание: Уточните телефон")).toBeInTheDocument();
    expect(row("Андреева Елена")).toHaveClass("is-flagged");
    await user.click(screen.getByRole("button", { name: "С замечаниями 1" }));
    expect(screen.queryByText("Алексеев Пётр", NAME)).not.toBeInTheDocument();
  });

  it("комментарий к студенту уходит с student_id, ко всему ответу — с null; лента обновляется", async () => {
    const user = setup();
    open(detail());
    await screen.findByText("Алексеев Пётр", NAME);
    post.mockResolvedValue({});
    const fresh = detail({ comments: [{ id: 9, student_id: 11, author_name: "Тестов Тест", text: "Нет справки", created_at: "2026-10-04T07:00:00" }] });
    get.mockResolvedValue(fresh);
    await user.selectOptions(screen.getByRole("combobox", { name: "К кому комментарий" }), "11");
    await user.type(screen.getByRole("textbox", { name: "Комментарий" }), "Нет справки");
    await user.click(screen.getByRole("button", { name: "Отправить комментарий" }));
    expect(post).toHaveBeenCalledWith("/tasks/assignments/5/comments", { text: "Нет справки", student_id: 11 });
    const thread = screen.getByRole("region", { name: "Обсуждение" });
    expect(await within(thread).findByText("Нет справки")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Комментарий" })).toHaveValue("");

    await user.type(screen.getByRole("textbox", { name: "Комментарий" }), "Всё ясно");
    await user.click(screen.getByRole("button", { name: "Отправить комментарий" }));
    expect(post).toHaveBeenLastCalledWith("/tasks/assignments/5/comments", { text: "Всё ясно", student_id: null });
  });

  it("у группового ответа нет выбора студента", async () => {
    open(detail({ collect_mode: "group", rows: [] }));
    await screen.findByRole("region", { name: "Обсуждение" });
    expect(screen.queryByRole("combobox", { name: "К кому комментарий" })).not.toBeInTheDocument();
  });
});

describe("TaskAssignmentPage — черновик при уходе", () => {
  afterEach(() => sessionStorage.clear());

  it("несохранённые правки сохраняются во вкладке и подставляются при возвращении", async () => {
    const user = setup();
    put.mockRejectedValue(new ApiError(0, "нет связи"));
    const first = open(detail());
    await screen.findByText("Алексеев Пётр", NAME);
    await user.type(screen.getByRole("textbox", { name: "Телефон родителя: Алексеев Пётр" }), "+7 905");
    await autosave();
    expect(await screen.findByText(/Не сохранено/)).toBeInTheDocument();
    first.unmount();

    put.mockResolvedValue(detail({ status: "in_progress" }));
    open(detail());
    expect(await screen.findByRole("textbox", { name: "Телефон родителя: Алексеев Пётр" })).toHaveValue("+7 905");
    await autosave();
    expect(put).toHaveBeenLastCalledWith("/tasks/assignments/5/answers", expect.objectContaining({
      rows: expect.arrayContaining([expect.objectContaining({ student_id: 11, values: { f3: "+7 905" } })]),
    }));
    await waitFor(() => expect(sessionStorage.getItem("task-draft-5")).toBeNull());
  });

  it("у отправленного ответа старый черновик не подставляется и удаляется", async () => {
    sessionStorage.setItem("task-draft-5", JSON.stringify({ rows: { 11: { is_included: true, values: { f3: "старое" } } }, groupValues: {} }));
    open(detail({ status: "submitted", can_edit: false, can_submit: false }));
    await screen.findByText("Алексеев Пётр", NAME);
    expect(screen.queryByText("старое")).not.toBeInTheDocument();
    expect(sessionStorage.getItem("task-draft-5")).toBeNull();
  });
});
