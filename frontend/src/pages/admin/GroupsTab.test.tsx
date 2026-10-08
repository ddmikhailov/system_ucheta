import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../../api/client";
import type { StudyGroupAdmin, UserAdmin } from "../../api/types";
import { renderPage } from "../../test/utils";
import { todayIso } from "../../utils/date";
import GroupsTab from "./GroupsTab";
import { chooseOption } from "../../test/searchSelect";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);
const patch = vi.mocked(api.patch);
const del = vi.mocked(api.delete);

const DEPARTMENTS = [
  { id: 1, name: "Диджитал", is_active: true },
  { id: 2, name: "Моссовет", is_active: true },
];

function group(id: number, code: string, over: Partial<StudyGroupAdmin> = {}): StudyGroupAdmin {
  return {
    id, code, course: 1, department_id: 1, study_form: null, is_active: true, curator_name: "Иванова А.",
    curator_assignment_id: 100 + id, deputy_name: null, deputy_assignment_id: null, ...over,
  };
}

const USERS: UserAdmin[] = [
  { id: 11, username: "k1", full_name: "Куратор Первый", role: "curator", display_title: null, department_id: 1, is_active: true, has_password: true, must_change_password: false },
  { id: 12, username: "p1", full_name: "Психолог Павел", role: "psychologist", display_title: null, department_id: 1, is_active: true, has_password: true, must_change_password: false },
  { id: 13, username: "a1", full_name: "Админов Админ", role: "admin", display_title: null, department_id: null, is_active: true, has_password: true, must_change_password: false },
  { id: 14, username: "k2", full_name: "Архивный Куратор", role: "curator", display_title: null, department_id: 1, is_active: false, has_password: true, must_change_password: false },
];

let groups: StudyGroupAdmin[];

beforeEach(() => {
  for (const fn of [post, patch, del]) fn.mockReset();
  groups = [
    group(1, "СА172", { study_form: "очная", deputy_name: "Заместов З.", deputy_assignment_id: 201 }),
    group(2, "ИИ112", { curator_name: null, curator_assignment_id: null }),
    group(3, "АРХ-1", { is_active: false }),
  ];
  get.mockReset();
  get.mockImplementation(async (path: string) => {
    if (path === "/admin/groups") return groups;
    if (path === "/admin/departments") return DEPARTMENTS;
    if (path === "/admin/users") return USERS;
    if (path.endsWith("/deletion-preview")) {
      return { code: "СА172", students: 25, attendance_marks: 800, day_submissions: 30, absence_periods: 2, curator_assignments: 3 };
    }
    return [];
  });
});

const row = (code: string) => screen.getByText(code).closest("tr") as HTMLElement;

async function openGroup(code: string, role = "admin") {
  const u = userEvent.setup();
  renderPage(<GroupsTab canEdit canCreate />, { role, user: { department_name: "Диджитал" } });
  await u.click(await screen.findByRole("button", { name: code }));
  return { u, dialog: await screen.findByRole("dialog", { name: code }) };
}

describe("GroupsTab — список", () => {
  it("показывает код, курс, форму, куратора; без куратора строка помечена; архив спрятан", async () => {
    const u = userEvent.setup();
    renderPage(<GroupsTab canEdit canCreate />, { role: "admin" });
    await screen.findByRole("button", { name: "СА172" });
    expect(within(row("СА172")).getByText("очная")).toBeInTheDocument();
    expect(within(row("СА172")).getByText("Иванова А.")).toBeInTheDocument();
    expect(within(row("ИИ112")).getByText("нет куратора")).toBeInTheDocument();
    expect(row("ИИ112")).toHaveClass("not-submitted-row");
    expect(screen.queryByText("АРХ-1")).not.toBeInTheDocument();
    await u.click(screen.getByRole("button", { name: "Отключённые (1)" }));
    expect(within(row("АРХ-1")).getByText("нет")).toBeInTheDocument();
  });

  it("переключатель «Активна» отключает группу сразу из списка и сообщает, что она выпала из свода", async () => {
    const u = userEvent.setup();
    patch.mockResolvedValue({});
    renderPage(<GroupsTab canEdit canCreate />, { role: "admin" });
    await screen.findByRole("button", { name: "СА172" });

    await u.click(screen.getByRole("switch", { name: "Активна: СА172" }));

    expect(patch).toHaveBeenCalledWith("/admin/groups/1", { is_active: false });
    expect(await screen.findByText(/Группа «СА172» отключена: в свод и общие списки не попадает/)).toBeInTheDocument();
  });

  it("отключённую группу можно включить тем же переключателем", async () => {
    const u = userEvent.setup();
    patch.mockResolvedValue({});
    renderPage(<GroupsTab canEdit canCreate />, { role: "admin" });
    await u.click(await screen.findByRole("button", { name: "Отключённые (1)" }));

    await u.click(screen.getByRole("switch", { name: "Активна: АРХ-1" }));

    expect(patch).toHaveBeenCalledWith("/admin/groups/3", { is_active: true });
    expect(await screen.findByText(/Группа «АРХ-1» включена/)).toBeInTheDocument();
  });

  it("без права правки переключателя нет — только «да/нет»", async () => {
    renderPage(<GroupsTab canEdit={false} canCreate={false} />, { role: "admin" });
    await screen.findByText("СА172");
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(within(row("СА172")).getByText("да")).toBeInTheDocument();
  });

  it("без права правки код — просто текст, формы добавления нет", async () => {
    renderPage(<GroupsTab canEdit={false} canCreate={false} />, { role: "edu_department" });
    await screen.findByText("СА172");
    expect(screen.queryByRole("button", { name: "СА172" })).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Код группы")).not.toBeInTheDocument();
  });
});

describe("GroupsTab — создание", () => {
  it("создаёт группу в выбранном отделении; форма обучения необязательна", async () => {
    const u = userEvent.setup();
    post.mockResolvedValue({});
    renderPage(<GroupsTab canEdit canCreate />, { role: "admin" });
    await screen.findByText("СА172");
    await u.type(screen.getByPlaceholderText("Код группы"), "КБ101");
    await u.selectOptions(screen.getByLabelText("Отделение"), "2");
    await u.click(screen.getByRole("button", { name: "Добавить группу" }));
    expect(post).toHaveBeenCalledWith("/admin/groups", { code: "КБ101", course: 1, department_id: 2, study_form: null });
    await waitFor(() => expect(screen.getByPlaceholderText("Код группы")).toHaveValue(""));
  });

  it("зав. отделением и тьютор создают только в своём отделении", async () => {
    renderPage(<GroupsTab canEdit canCreate />, { role: "dept_head", user: { department_name: "Моссовет" } });
    await screen.findByText("СА172");
    expect(within(screen.getByLabelText("Отделение")).getAllByRole("option").map((o) => o.textContent)).toEqual(["Моссовет"]);
  });

  it("дубликат кода — сообщение сервера, введённое остаётся", async () => {
    const u = userEvent.setup();
    post.mockRejectedValue(new ApiError(409, "Группа с таким кодом уже существует"));
    renderPage(<GroupsTab canEdit canCreate />, { role: "admin" });
    await screen.findByText("СА172");
    await u.type(screen.getByPlaceholderText("Код группы"), "СА172");
    await u.click(screen.getByRole("button", { name: "Добавить группу" }));
    expect(await screen.findByText("Группа с таким кодом уже существует")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Код группы")).toHaveValue("СА172");
  });
});

describe("GroupsTab — окно группы", () => {
  it("сохраняет код, курс и форму обучения", async () => {
    const { u, dialog } = await openGroup("СА172");
    patch.mockResolvedValue({});
    const code = within(dialog).getByDisplayValue("СА172");
    await u.clear(code);
    await u.type(code, "СА172-26");
    await u.click(within(dialog).getByRole("button", { name: "Сохранить" }));
    expect(patch).toHaveBeenCalledWith("/admin/groups/1", { code: "СА172-26", course: 1, study_form: "очная" });
  });

  it("ошибка сохранения показывается внутри окна", async () => {
    const { u, dialog } = await openGroup("СА172");
    patch.mockRejectedValue(new ApiError(409, "Группа с таким кодом уже существует"));
    await u.click(within(dialog).getByRole("button", { name: "Сохранить" }));
    expect(await within(dialog).findByText("Группа с таким кодом уже существует")).toBeInTheDocument();
  });

  it("отключить и включить обратно; окно закрывается", async () => {
    const { u, dialog } = await openGroup("СА172");
    patch.mockResolvedValue({});
    await u.click(within(dialog).getByRole("button", { name: "Отключить группу" }));
    expect(patch).toHaveBeenCalledWith("/admin/groups/1", { is_active: false });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("куратор и заместитель показаны, у вакантной группы — «Назначить куратора» без «Снять»", async () => {
    const { dialog } = await openGroup("СА172");
    expect(within(dialog).getByText(/Куратор: Иванова А\./)).toBeInTheDocument();
    expect(within(dialog).getByText(/Заместитель: Заместов З\./)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Сменить куратора" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Снять заместителя" })).toBeInTheDocument();

    const vacant = await openGroup("ИИ112");
    expect(within(vacant.dialog).getByRole("button", { name: "Назначить куратора" })).toBeInTheDocument();
    expect(within(vacant.dialog).queryByRole("button", { name: "Снять куратора" })).not.toBeInTheDocument();
    expect(within(vacant.dialog).getByRole("button", { name: "Назначить заместителя" })).toBeInTheDocument();
  });

  it("снять куратора / заместителя — после подтверждения, по id назначения", async () => {
    const { u, dialog } = await openGroup("СА172");
    post.mockResolvedValue({});
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    await u.click(within(dialog).getByRole("button", { name: "Снять куратора" }));
    expect(post).not.toHaveBeenCalled();
    confirm.mockReturnValueOnce(true);
    await u.click(within(dialog).getByRole("button", { name: "Снять куратора" }));
    expect(post).toHaveBeenCalledWith("/admin/curator-assignments/101/end");
    confirm.mockReturnValueOnce(true);
    await u.click(within(dialog).getByRole("button", { name: "Снять заместителя" }));
    expect(post).toHaveBeenLastCalledWith("/admin/curator-assignments/201/end");
  });
});

describe("GroupsTab — назначение куратора и заместителя", () => {
  it("«Сменить заместителя» открывает окно сразу на роли «Заместитель», «Сменить куратора» — на «Основной куратор»", async () => {
    const { u, dialog } = await openGroup("СА172");
    await u.click(within(dialog).getByRole("button", { name: "Сменить заместителя" }));
    const modal = await screen.findByRole("dialog", { name: "Назначить куратора" });
    expect(within(modal).getByLabelText("Роль")).toHaveValue("deputy");
    await u.click(within(modal).getByRole("button", { name: "Отмена" }));

    await u.click(within(dialog).getByRole("button", { name: "Сменить куратора" }));
    expect(within(await screen.findByRole("dialog", { name: "Назначить куратора" })).getByLabelText("Роль")).toHaveValue("curator");
  });

  it("в списке — активные куратор/заместитель/соц. педагог/психолог; администратор и архивные не предлагаются", async () => {
    const { u, dialog } = await openGroup("СА172");
    await u.click(within(dialog).getByRole("button", { name: "Сменить куратора" }));
    const modal = await screen.findByRole("dialog", { name: "Назначить куратора" });
    await u.click(within(modal).getByLabelText("Куратор"));
    const options = within(within(modal).getByRole("listbox")).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Куратор Первый", "Психолог Павел"]);
  });

  it("сохраняет назначение с ролью и датой, закрывает окно и перезагружает список", async () => {
    const { u, dialog } = await openGroup("ИИ112");
    post.mockResolvedValue({});
    await u.click(within(dialog).getByRole("button", { name: "Назначить заместителя" }));
    const modal = await screen.findByRole("dialog", { name: "Назначить куратора" });
    await chooseOption(u, within(modal).getByLabelText("Куратор"), "Психолог Павел");
    const loadsBefore = get.mock.calls.filter((c) => c[0] === "/admin/groups").length;
    await u.click(within(modal).getByRole("button", { name: "Сохранить" }));
    expect(post).toHaveBeenCalledWith("/admin/curator-assignments", {
      study_group_id: 2, user_id: 12, role_type: "deputy", start_date: todayIso(),
    });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Назначить куратора" })).not.toBeInTheDocument());
    await waitFor(() => expect(get.mock.calls.filter((c) => c[0] === "/admin/groups").length).toBe(loadsBefore + 1));
  });

  it("ошибка назначения показывается в окне назначения", async () => {
    const { u, dialog } = await openGroup("СА172");
    post.mockRejectedValue(new ApiError(403, "Куратор не из вашего отделения"));
    await u.click(within(dialog).getByRole("button", { name: "Сменить куратора" }));
    const modal = await screen.findByRole("dialog", { name: "Назначить куратора" });
    await u.click(within(modal).getByRole("button", { name: "Сохранить" }));
    expect(await within(modal).findByText("Куратор не из вашего отделения")).toBeInTheDocument();
  });

  it("некого назначать — сообщение вместо формы", async () => {
    get.mockImplementation(async (path: string) => {
      if (path === "/admin/groups") return groups;
      if (path === "/admin/departments") return DEPARTMENTS;
      return [];
    });
    const { u, dialog } = await openGroup("СА172");
    await u.click(within(dialog).getByRole("button", { name: "Сменить куратора" }));
    const modal = await screen.findByRole("dialog", { name: "Назначить куратора" });
    expect(within(modal).getByText(/нет ни одного куратора/)).toBeInTheDocument();
    expect(within(modal).queryByRole("button", { name: "Сохранить" })).not.toBeInTheDocument();
  });
});

describe("GroupsTab — удаление группы", () => {
  it("администратор и тьютор: «Удалить группу навсегда…» с предпросмотром и вводом кода", async () => {
    for (const role of ["admin", "tutor"]) {
      const { dialog } = await openGroup("СА172", role);
      expect(within(dialog).getByRole("button", { name: "Удалить группу навсегда…" })).toBeInTheDocument();
      expect(within(dialog).queryByRole("button", { name: "Удалить насовсем" })).not.toBeInTheDocument();
      document.body.innerHTML = "";
    }
  });

  it("зав. отделением навсегда не удаляет: у архивной группы — обычное «Удалить насовсем», у активной кнопки нет", async () => {
    const u = userEvent.setup();
    renderPage(<GroupsTab canEdit canCreate />, { role: "dept_head", user: { department_name: "Диджитал" } });
    await u.click(await screen.findByRole("button", { name: "СА172" }));
    let dialog = await screen.findByRole("dialog", { name: "СА172" });
    expect(within(dialog).queryByRole("button", { name: /Удалить/ })).not.toBeInTheDocument();
    await u.click(within(dialog).getByRole("button", { name: "Закрыть" }));

    await u.click(screen.getByRole("button", { name: "Отключённые (1)" }));
    await u.click(screen.getByRole("button", { name: "АРХ-1" }));
    dialog = await screen.findByRole("dialog", { name: "АРХ-1" });
    del.mockResolvedValue({ deleted: true, anonymized: false, detail: "Группа удалена" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await u.click(within(dialog).getByRole("button", { name: "Удалить насовсем" }));
    expect(del).toHaveBeenCalledWith("/admin/groups/3");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByText("Группа удалена")).toBeInTheDocument();
  });

  it("обычное удаление: отказ в подтверждении ничего не отправляет, ошибка сервера показывается", async () => {
    const u = userEvent.setup();
    renderPage(<GroupsTab canEdit canCreate />, { role: "dept_head", user: { department_name: "Диджитал" } });
    await u.click(await screen.findByRole("button", { name: "Отключённые (1)" }));
    await u.click(screen.getByRole("button", { name: "АРХ-1" }));
    const dialog = await screen.findByRole("dialog", { name: "АРХ-1" });
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    await u.click(within(dialog).getByRole("button", { name: "Удалить насовсем" }));
    expect(del).not.toHaveBeenCalled();
    confirm.mockReturnValueOnce(true);
    del.mockRejectedValue(new ApiError(409, "У группы есть история — оставьте её в архиве"));
    await u.click(within(dialog).getByRole("button", { name: "Удалить насовсем" }));
    expect(await screen.findByText(/оставьте её в архиве/)).toBeInTheDocument();
  });
});

describe("GroupsTab — фильтры и сортировка", () => {
  const codes = () => Array.from(document.querySelectorAll(".dash-table tbody tr td:first-child")).map((td) => td.textContent);

  beforeEach(() => {
    groups = [
      group(1, "СА172", { course: 1 }),
      group(2, "ИИ212", { course: 2, curator_name: null, curator_assignment_id: null }),
      group(3, "ИТ301", { course: 3 }),
    ];
  });

  it("поиск по коду и куратору, курс, «только без куратора», счётчик и сброс", async () => {
    const u = userEvent.setup();
    renderPage(<GroupsTab canEdit canCreate />, { role: "admin" });
    await screen.findByRole("button", { name: "СА172" });
    expect(screen.getByRole("status")).toHaveTextContent("Показано 3 из 3");

    await u.click(screen.getByLabelText("Только без куратора"));
    expect(codes()).toEqual(["ИИ212"]);
    await u.click(screen.getByRole("button", { name: "Сбросить фильтры" }));
    expect(codes()).toHaveLength(3);

    await u.selectOptions(screen.getByLabelText("Фильтр по курсу"), "3");
    expect(codes()).toEqual(["ИТ301"]);
    await u.selectOptions(screen.getByLabelText("Фильтр по курсу"), "all");

    await u.type(screen.getByLabelText("Поиск по группе или куратору"), "иит");
    expect(codes()).toEqual(["Под выбранные фильтры ничего не подошло."]);
  });

  it("сортировка по заголовку «Курс»: вверх, вниз", async () => {
    const u = userEvent.setup();
    renderPage(<GroupsTab canEdit canCreate />, { role: "admin" });
    await screen.findByRole("button", { name: "СА172" });
    await u.click(screen.getByRole("button", { name: /^Курс/ }));
    await u.click(screen.getByRole("button", { name: /^Курс/ }));
    expect(codes()).toEqual(["ИТ301", "ИИ212", "СА172"]);
  });
});
