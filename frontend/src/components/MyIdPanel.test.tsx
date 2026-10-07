import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { MyIdData, MyIdRow } from "../api/types";
import { renderPage } from "../test/utils";
import MyIdPanel from "./MyIdPanel";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const put = vi.mocked(api.put);

const GROUPS = [{ id: 7, code: "СА172", course: 1 }];

function row(id: number, name: string, over: Partial<MyIdRow> = {}): MyIdRow {
  return {
    student_id: id, full_name: name, biometrics: null, biometrics_reason: null, max_student: null, max_student_reason: null,
    max_parent: null, max_parent_reason: null, ...over,
  };
}

function data(rows: MyIdRow[], over: Partial<MyIdData> = {}): MyIdData {
  return {
    group_id: 7, group_code: "СА172", school_year: "2026-2027", can_edit: true, rows,
    totals: { students: rows.length, biometrics_yes: 0, biometrics_no: 0, biometrics_unset: rows.length, max_student_yes: 0, max_student_no: 0, max_parent_yes: 0, max_parent_no: 0 },
    ...over,
  };
}

function mock(d: MyIdData) {
  get.mockImplementation(async (path: string) => {
    if (path === "/individual-work/groups") return GROUPS;
    if (path === "/my-id/groups/7") return d;
    throw new Error(`неожиданный запрос ${path}`);
  });
}

const BIO = "Биометрия «Мой.ID»";
const MAX_STUDENT = "Студент в чате MAX";
const reasonLabel = (text: string, name: string) => `${text}: ${name}`;

/** Пара кнопок «Да» / «Нет» показателя у студента. */
function pair(label: string, name: string) {
  const group = screen.getByRole("group", { name: `${label}: ${name}` });
  return { yes: within(group).getByRole("button", { name: "Да" }), no: within(group).getByRole("button", { name: "Нет" }) };
}

const ROWS = [row(1, "Алексеев Пётр"), row(2, "Андреева Елена", { biometrics: true, max_student: false, max_student_reason: "не пользуется" })];

beforeEach(() => {
  get.mockReset();
  put.mockReset();
});

describe("MyIdPanel — «Мой ID»: две кнопки «Да» / «Нет»", () => {
  it("пока ответа нет, обе кнопки неактивны (не нажаты) и доступны; поля причины нет и чёрточек нет", async () => {
    mock(data(ROWS));
    renderPage(<MyIdPanel />, { role: "curator" });
    await screen.findByText("Алексеев Пётр");
    const { yes, no } = pair(BIO, "Алексеев Пётр");
    expect(yes).toHaveAttribute("aria-pressed", "false");
    expect(no).toHaveAttribute("aria-pressed", "false");
    expect(yes).toBeEnabled();
    expect(no).toBeEnabled();
    expect(screen.queryByLabelText(reasonLabel("Причина отсутствия биометрии", "Алексеев Пётр"))).not.toBeInTheDocument();
    const firstRow = screen.getByText("Алексеев Пётр").closest("tr") as HTMLElement;
    expect(within(firstRow).queryByText("—")).not.toBeInTheDocument(); // «чёрточек» рядом с кнопками нет
    expect(document.querySelectorAll("table select")).toHaveLength(0); // выпадающих списков в таблице больше нет
  });

  it("сохранённые ответы показаны нажатой кнопкой и заблокированы: исправить нельзя", async () => {
    mock(data(ROWS));
    renderPage(<MyIdPanel />, { role: "curator" });
    await screen.findByText("Андреева Елена");
    const bio = pair(BIO, "Андреева Елена");
    expect(bio.yes).toHaveAttribute("aria-pressed", "true");
    expect(bio.no).toHaveAttribute("aria-pressed", "false");
    expect(bio.yes).toBeDisabled();
    expect(bio.no).toBeDisabled();
    const maxStudent = pair(MAX_STUDENT, "Андреева Елена");
    expect(maxStudent.no).toHaveAttribute("aria-pressed", "true");
    expect(maxStudent.yes).toBeDisabled();
    // а там, где ответа не было, кнопки по-прежнему доступны
    expect(pair("Родитель в чате MAX", "Андреева Елена").yes).toBeEnabled();
  });

  it("поле причины появляется только после «Нет», пустое — поле для ввода; «Да» его не показывает", async () => {
    const user = userEvent.setup();
    mock(data(ROWS));
    renderPage(<MyIdPanel />, { role: "curator" });
    await screen.findByText("Алексеев Пётр");
    const label = reasonLabel("Причина отсутствия биометрии", "Алексеев Пётр");
    await user.click(pair(BIO, "Алексеев Пётр").yes);
    expect(screen.queryByLabelText(label)).not.toBeInTheDocument();
    await user.click(pair(BIO, "Алексеев Пётр").no); // пока не сохранено — можно передумать
    const reason = screen.getByLabelText(label);
    expect(reason).toHaveValue("");
    expect(reason).toBeEnabled();
    expect(reason.tagName).toBe("INPUT");
  });

  it("ответы и причина сохраняются одним запросом; сохранённое потом блокируется", async () => {
    const user = userEvent.setup();
    mock(data(ROWS));
    put.mockResolvedValue(data([row(1, "Алексеев Пётр", { biometrics: false, biometrics_reason: "тех. трудности" }), ROWS[1]]));
    renderPage(<MyIdPanel />, { role: "curator" });
    await screen.findByText("Алексеев Пётр");
    await user.click(pair(BIO, "Алексеев Пётр").no);
    await user.type(screen.getByLabelText(reasonLabel("Причина отсутствия биометрии", "Алексеев Пётр")), "тех. трудности");
    expect(screen.getByRole("button", { name: "Сохранить (1)" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Сохранить (1)" }));
    expect(put).toHaveBeenCalledWith("/my-id/groups/7", { rows: [{
      student_id: 1, biometrics: false, biometrics_reason: "тех. трудности", max_student: null, max_student_reason: null,
      max_parent: null, max_parent_reason: null,
    }] });
    expect(await screen.findByText("Сохранено")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeDisabled();
    expect(pair(BIO, "Алексеев Пётр").no).toBeDisabled(); // теперь ответ заблокирован
    expect(screen.getByLabelText(reasonLabel("Причина отсутствия биометрии", "Алексеев Пётр"))).toBeEnabled(); // причину дописать можно
  });

  it("у уже сохранённого «Нет» причину можно дописать, не трогая ответ", async () => {
    const user = userEvent.setup();
    mock(data(ROWS));
    put.mockResolvedValue(data(ROWS));
    renderPage(<MyIdPanel />, { role: "curator" });
    await screen.findByText("Андреева Елена");
    const reason = screen.getByLabelText(reasonLabel("Причина: нет MAX у студента", "Андреева Елена"));
    await user.type(reason, " (с 1 сентября)");
    await user.click(screen.getByRole("button", { name: "Сохранить (1)" }));
    const sent = put.mock.calls[0][1] as { rows: MyIdRow[] };
    expect(sent.rows[0]).toMatchObject({ student_id: 2, max_student: false, max_student_reason: "не пользуется (с 1 сентября)", biometrics: true });
  });

  it("итоги Да / Нет пересчитываются сразу, до сохранения", async () => {
    const user = userEvent.setup();
    mock(data(ROWS));
    renderPage(<MyIdPanel />, { role: "curator" });
    await screen.findByText("Алексеев Пётр");
    const summary = () => document.querySelector(".my-id-summary");
    expect(summary()).toHaveTextContent("Биометрия зарегистрирована: 1 из 2");
    await user.click(pair(BIO, "Алексеев Пётр").yes);
    expect(summary()).toHaveTextContent("Биометрия зарегистрирована: 2 из 2");
    const footer = screen.getByText("Итого").closest("tr") as HTMLElement;
    expect(footer).toHaveTextContent("Да: 2 · Нет: 0");
  });

  it("ошибка сохранения (в том числе «исправить нельзя») показывается, выбор остаётся", async () => {
    const user = userEvent.setup();
    mock(data(ROWS));
    put.mockRejectedValue(new ApiError(409, "Ответ уже сохранён — исправить его нельзя"));
    renderPage(<MyIdPanel />, { role: "curator" });
    await screen.findByText("Алексеев Пётр");
    await user.click(pair(MAX_STUDENT, "Алексеев Пётр").yes);
    await user.click(screen.getByRole("button", { name: "Сохранить (1)" }));
    expect(await screen.findByText("Ответ уже сохранён — исправить его нельзя")).toBeInTheDocument();
    expect(pair(MAX_STUDENT, "Алексеев Пётр").yes).toHaveAttribute("aria-pressed", "true");
  });

  it("только чтение: кнопки заблокированы, кнопки сохранения нет", async () => {
    mock(data(ROWS, { can_edit: false }));
    renderPage(<MyIdPanel />, { role: "social_pedagogue" });
    await screen.findByText("Алексеев Пётр");
    expect(pair(BIO, "Алексеев Пётр").yes).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Сохранить/ })).not.toBeInTheDocument();
  });

  it("вкладка группы куратора (fixedGroupId): выбора группы нет, список групп не запрашивается", async () => {
    mock(data(ROWS));
    renderPage(<MyIdPanel fixedGroupId={7} />, { role: "curator" });
    expect(await screen.findByText("Алексеев Пётр")).toBeInTheDocument();
    expect(get).not.toHaveBeenCalledWith("/individual-work/groups");
    expect(screen.queryByLabelText("Группа")).not.toBeInTheDocument();
  });

  it("нет групп и пустая группа — подсказки; ошибка загрузки видна", async () => {
    get.mockImplementation(async () => []);
    const first = renderPage(<MyIdPanel />, { role: "curator" });
    expect(await screen.findByText("Нет доступных групп.")).toBeInTheDocument();
    first.unmount();

    mock(data([]));
    const second = renderPage(<MyIdPanel />, { role: "curator" });
    expect(await screen.findByText("В группе СА172 нет студентов.")).toBeInTheDocument();
    second.unmount();

    get.mockImplementation(async (path: string) => {
      if (path === "/individual-work/groups") return GROUPS;
      throw new ApiError(403, "Это не ваша группа");
    });
    renderPage(<MyIdPanel />, { role: "curator" });
    await waitFor(() => expect(screen.getByText("Это не ваша группа")).toBeInTheDocument());
  });
});
