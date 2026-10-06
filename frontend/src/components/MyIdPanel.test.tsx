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

const ROWS = [row(1, "Алексеев Пётр"), row(2, "Андреева Елена", { biometrics: true, max_student: false, max_student_reason: "не пользуется" })];

beforeEach(() => {
  get.mockReset();
  put.mockReset();
});

describe("MyIdPanel — вкладка «Мой ID»", () => {
  it("показывает студентов группы с их отметками и итогами", async () => {
    mock(data(ROWS));
    renderPage(<MyIdPanel />, { role: "curator" });
    expect(await screen.findByText("Алексеев Пётр")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/my-id/groups/7");
    const second = screen.getByText("Андреева Елена").closest("tr") as HTMLElement;
    expect(within(second).getByLabelText("Биометрия «Мой.ID»: Андреева Елена")).toHaveValue("yes");
    expect(within(second).getByLabelText("Студент в чате MAX: Андреева Елена")).toHaveValue("no");
    expect(within(second).getByLabelText("Причина: нет MAX у студента: Андреева Елена")).toHaveValue("не пользуется");
    const summary = document.querySelector(".my-id-summary");
    expect(summary).toHaveTextContent("Биометрия зарегистрирована: 1 из 2");
    expect(summary).toHaveTextContent("Не зарегистрированы: 1");
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeDisabled();
  });

  it("«НЕТ» открывает поле причины, «ДА» убирает его; сохраняются только изменённые студенты", async () => {
    const user = userEvent.setup();
    mock(data(ROWS));
    put.mockResolvedValue(data([row(1, "Алексеев Пётр", { biometrics: false, biometrics_reason: "тех. трудности" }), ROWS[1]]));
    renderPage(<MyIdPanel />, { role: "curator" });
    await screen.findByText("Алексеев Пётр");
    expect(screen.queryByLabelText("Причина отсутствия биометрии: Алексеев Пётр")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Биометрия «Мой.ID»: Алексеев Пётр"), "no");
    await user.type(await screen.findByLabelText("Причина отсутствия биометрии: Алексеев Пётр"), "тех. трудности");
    expect(screen.getByRole("button", { name: "Сохранить (1)" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Сохранить (1)" }));
    expect(put).toHaveBeenCalledWith("/my-id/groups/7", { rows: [{
      student_id: 1, biometrics: false, biometrics_reason: "тех. трудности", max_student: null, max_student_reason: null,
      max_parent: null, max_parent_reason: null,
    }] });
    expect(await screen.findByText("Сохранено")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeDisabled();
  });

  it("смена «НЕТ» на «ДА» стирает причину в отправляемых данных", async () => {
    const user = userEvent.setup();
    mock(data(ROWS));
    put.mockResolvedValue(data(ROWS));
    renderPage(<MyIdPanel />, { role: "curator" });
    await screen.findByText("Андреева Елена");
    await user.selectOptions(screen.getByLabelText("Студент в чате MAX: Андреева Елена"), "yes");
    await user.click(screen.getByRole("button", { name: "Сохранить (1)" }));
    const sent = put.mock.calls[0][1] as { rows: MyIdRow[] };
    expect(sent.rows[0]).toMatchObject({ student_id: 2, max_student: true, max_student_reason: null });
  });

  it("итоги ДА/НЕТ пересчитываются сразу, до сохранения", async () => {
    const user = userEvent.setup();
    mock(data(ROWS));
    renderPage(<MyIdPanel />, { role: "curator" });
    await screen.findByText("Алексеев Пётр");
    const footer = screen.getByText("ДА / НЕТ").closest("tr") as HTMLElement;
    expect(within(footer).getAllByText("1")[0]).toBeInTheDocument(); // биометрия: 1 «ДА»
    await user.selectOptions(screen.getByLabelText("Биометрия «Мой.ID»: Алексеев Пётр"), "yes");
    expect(document.querySelector(".my-id-summary")).toHaveTextContent("Биометрия зарегистрирована: 2 из 2");
  });

  it("ошибка сохранения показывается, правки остаются", async () => {
    const user = userEvent.setup();
    mock(data(ROWS));
    put.mockRejectedValue(new ApiError(400, "Среди студентов есть не из этой группы"));
    renderPage(<MyIdPanel />, { role: "curator" });
    await user.selectOptions(await screen.findByLabelText("Студент в чате MAX: Алексеев Пётр"), "yes");
    await user.click(screen.getByRole("button", { name: "Сохранить (1)" }));
    expect(await screen.findByText("Среди студентов есть не из этой группы")).toBeInTheDocument();
    expect(screen.getByLabelText("Студент в чате MAX: Алексеев Пётр")).toHaveValue("yes");
  });

  it("только чтение: поля заблокированы, кнопки сохранения нет", async () => {
    mock(data(ROWS, { can_edit: false }));
    renderPage(<MyIdPanel />, { role: "social_pedagogue" });
    expect(await screen.findByLabelText("Биометрия «Мой.ID»: Алексеев Пётр")).toBeDisabled();
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
