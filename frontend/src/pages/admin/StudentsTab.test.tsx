import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../../api/client";
import { renderPage } from "../../test/utils";
import { todayIso } from "../../utils/date";
import StudentsTab from "./StudentsTab";
import { chooseOption } from "../../test/searchSelect";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);

const GROUPS = [
  { id: 7, code: "СА172", course: 1, is_active: true },
  { id: 8, code: "ИИ112", course: 2, is_active: true },
  { id: 9, code: "АРХ-1", course: 3, is_active: false },
];

const student = (id: number, name: string, over = {}) => ({
  id, full_name: name, last_name: name.split(" ")[0], first_name: name.split(" ")[1], middle_name: null,
  study_group_id: 7, status: "studying", enrolled_at: "2026-09-01", left_at: null, ...over,
});

const IN_GROUP = [
  student(1, "Алексеев Пётр"),
  student(2, "Андреева Елена", { status: "academic_leave", left_at: "2026-09-20" }),
  student(3, "Волков Иван", { status: "expelled", left_at: "2026-09-25" }),
];

const studentCalls = () => get.mock.calls.map((c) => String(c[0])).filter((p) => p.startsWith("/admin/students"));

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  get.mockImplementation(async (path: string) => {
    if (path === "/admin/groups") return GROUPS;
    if (path === "/admin/students?study_group_id=7") return IN_GROUP;
    if (path === "/admin/students?study_group_id=8") return [student(4, "Захаров Андрей", { study_group_id: 8 })];
    if (path === "/admin/students") return [...IN_GROUP, student(4, "Захаров Андрей", { study_group_id: 8 })];
    return [];
  });
});

describe("StudentsTab", () => {
  it("грузит активные группы, показывает студентов первой; даты в формате ДД.ММ.ГГГГ", async () => {
    renderPage(<StudentsTab canCreate />);
    const link = await screen.findByRole("link", { name: "Алексеев Пётр" });
    expect(link).toHaveAttribute("href", "/students/1");
    expect(screen.queryByRole("option", { name: /АРХ-1/ })).not.toBeInTheDocument(); // архивная группа
    const row = link.closest("tr") as HTMLElement;
    expect(within(row).getByText("01.09.2026")).toBeInTheDocument();
    expect(within(row).getByText("СА172")).toBeInTheDocument();
    expect(studentCalls()).toEqual(["/admin/students?study_group_id=7"]);
  });

  it("отчисленные и в академе спрятаны в архив, который раскрывается по клику", async () => {
    const user = userEvent.setup();
    renderPage(<StudentsTab canCreate />);
    await screen.findByRole("link", { name: "Алексеев Пётр" });
    expect(screen.queryByRole("link", { name: "Андреева Елена" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Архив (2)" }));
    const leave = screen.getByRole("link", { name: "Андреева Елена" }).closest("tr") as HTMLElement;
    expect(within(leave).getByText("20.09.2026")).toBeInTheDocument(); // дата выбытия
    expect(screen.getByRole("link", { name: "Волков Иван" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Скрыть архив" }));
    expect(screen.queryByRole("link", { name: "Волков Иван" })).not.toBeInTheDocument();
  });

  it("смена группы загружает её студентов", async () => {
    const user = userEvent.setup();
    renderPage(<StudentsTab canCreate />);
    await screen.findByRole("link", { name: "Алексеев Пётр" });
    await chooseOption(user, screen.getByRole("combobox"), /ИИ112/);
    expect(await screen.findByRole("link", { name: "Захаров Андрей" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Алексеев Пётр" })).not.toBeInTheDocument();
  });

  it("поиск по ФИО идёт по всем группам, блокирует выбор группы; пустой результат — своё сообщение", async () => {
    const user = userEvent.setup();
    renderPage(<StudentsTab canCreate />);
    await screen.findByRole("link", { name: "Алексеев Пётр" });
    const search = screen.getByPlaceholderText(/Поиск по ФИО/);
    await user.type(search, "захаров");
    expect(await screen.findByRole("link", { name: "Захаров Андрей" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Алексеев Пётр" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeDisabled();
    expect(studentCalls()).toContain("/admin/students");

    await user.clear(search);
    await user.type(search, "нет такого");
    expect(await screen.findByText("Никого не найдено.")).toBeInTheDocument();
    expect(screen.queryByText("В группе нет студентов.")).not.toBeInTheDocument();
  });

  it("пустая группа — сообщение про группу", async () => {
    get.mockImplementation(async (path: string) => (path === "/admin/groups" ? GROUPS : []));
    renderPage(<StudentsTab canCreate />);
    expect(await screen.findByText("В группе нет студентов.")).toBeInTheDocument();
  });

  it("добавляет студента в выбранную группу; отчество необязательно, форма очищается (кроме даты)", async () => {
    const user = userEvent.setup();
    post.mockResolvedValue({});
    renderPage(<StudentsTab canCreate />);
    await screen.findByRole("link", { name: "Алексеев Пётр" });
    await chooseOption(user, screen.getByRole("combobox"), /ИИ112/);
    await user.type(screen.getByPlaceholderText("Фамилия"), "Новиков");
    await user.type(screen.getByPlaceholderText("Имя"), "Олег");
    await user.click(screen.getByRole("button", { name: "Добавить студента" }));
    expect(post).toHaveBeenCalledWith("/admin/students", {
      last_name: "Новиков", first_name: "Олег", middle_name: null, study_group_id: 8, enrolled_at: todayIso(),
    });
    await waitFor(() => expect(screen.getByPlaceholderText("Фамилия")).toHaveValue(""));
  });

  it("ошибка добавления (чужое отделение) показывается, введённое остаётся", async () => {
    const user = userEvent.setup();
    post.mockRejectedValue(new ApiError(403, "Группа не относится к вашему отделению"));
    renderPage(<StudentsTab canCreate />, { role: "dept_head" });
    await screen.findByRole("link", { name: "Алексеев Пётр" });
    await user.type(screen.getByPlaceholderText("Фамилия"), "Новиков");
    await user.type(screen.getByPlaceholderText("Имя"), "Олег");
    await user.click(screen.getByRole("button", { name: "Добавить студента" }));
    expect(await screen.findByText("Группа не относится к вашему отделению")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Фамилия")).toHaveValue("Новиков");
  });

  it("без права создания формы добавления нет", async () => {
    renderPage(<StudentsTab canCreate={false} />, { role: "edu_department" });
    await screen.findByRole("link", { name: "Алексеев Пётр" });
    expect(screen.queryByPlaceholderText("Фамилия")).not.toBeInTheDocument();
  });

  it("сообщение после удаления студента приходит через состояние перехода и скрывается", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={[{ pathname: "/admin", state: { notice: "Студент удалён" } }]}>
        <StudentsTab canCreate />
      </MemoryRouter>
    );
    expect(await screen.findByText(/Студент удалён/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Скрыть" }));
    expect(screen.queryByText(/Студент удалён/)).not.toBeInTheDocument();
  });

  it("ошибка загрузки списка показывается", async () => {
    get.mockImplementation(async (path: string) => {
      if (path === "/admin/groups") return GROUPS;
      throw new ApiError(500, "Сервер недоступен");
    });
    renderPage(<StudentsTab canCreate />);
    expect(await screen.findByText("Сервер недоступен")).toBeInTheDocument();
  });
});
