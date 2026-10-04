import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, downloadFile } from "../api/client";
import { AuthContext } from "../auth/authContextObject";
import { makeUser } from "../test/utils";
import { todayIso } from "../utils/date";
import DashboardsPage from "./DashboardsPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }, downloadFile: vi.fn() };
});

// Свод и разбор по дням — отдельные большие компоненты: здесь проверяется, что страница им передаёт.
vi.mock("../components/AttendanceSummary", async () => ({
  default: (p: { canFilterDepartment: boolean }) => <div>свод, фильтр отделения={String(p.canFilterDepartment)}</div>,
}));
vi.mock("../components/CuratorDaysModal", async () => ({
  default: (p: { studyGroupId: number; onClose: () => void }) => (
    <div role="dialog" aria-label="Дисциплина по дням">
      группа {p.studyGroupId} <button onClick={p.onClose}>закрыть разбор</button>
    </div>
  ),
}));

const get = vi.mocked(api.get);
const download = vi.mocked(downloadFile);

const DAY = [
  { study_group_id: 1, code: "СА172", course: 1, responsible_name: "Иванова А.", in_list: 25, present: 23, late: 1, absent_excused: 1, absent_unexcused: 1, percent: 92.0, is_submitted: true, is_on_time: true },
  { study_group_id: 2, code: "ИИ212", course: 2, responsible_name: null, in_list: 20, present: null, late: null, absent_excused: null, absent_unexcused: null, percent: null, is_submitted: false, is_on_time: null },
  { study_group_id: 3, code: "ИТ301", course: 3, responsible_name: "Петров П.", in_list: 18, present: 18, late: 0, absent_excused: 0, absent_unexcused: 0, percent: 100, is_submitted: true, is_on_time: false },
];

const GROUPS = [
  { id: 1, code: "СА172", course: 1, department_id: 1, study_form: null, is_active: true, curator_name: "Иванова А.", curator_assignment_id: 1, deputy_name: null, deputy_assignment_id: null },
  { id: 2, code: "ИИ212", course: 2, department_id: 1, study_form: null, is_active: true, curator_name: null, curator_assignment_id: null, deputy_name: null, deputy_assignment_id: null },
  { id: 4, code: "АРХ-1", course: 1, department_id: 1, study_form: null, is_active: false, curator_name: null, curator_assignment_id: null, deputy_name: null, deputy_assignment_id: null },
];

function mockApi() {
  get.mockImplementation(async (path: string) => {
    if (path.startsWith("/dashboards/day")) return DAY;
    if (path.startsWith("/dashboards/dynamics")) {
      return [
        { date: "2026-10-01", in_list: 100, present: 96, percent: 96.0 },
        { date: "2026-10-02", in_list: 100, present: 80, percent: 80.0 },
        { date: "2026-10-03", in_list: null, present: null, percent: null },
      ];
    }
    if (path.startsWith("/dashboards/risk-students")) {
      return [{ student_id: 7, full_name: "Алексеев Пётр", group_code: "СА172", streak: 4 }];
    }
    if (path.startsWith("/dashboards/curator-discipline")) {
      return [
        { study_group_id: 1, code: "СА172", course: 1, responsible_name: "Иванова А.", on_time: 8, late: 1, missed: 0, total_study_days: 9 },
        { study_group_id: 2, code: "ИИ212", course: 2, responsible_name: null, on_time: 3, late: 2, missed: 4, total_study_days: 9 },
      ];
    }
    if (path === "/admin/groups") return GROUPS;
    if (path === "/admin/users") return [{ id: 11, username: "k1", full_name: "Куратор К.", role: "curator", display_title: null, department_id: 1, is_active: true, has_password: true, must_change_password: false, is_locked: false }];
    if (path === "/admin/departments") return [{ id: 1, name: "Диджитал", is_active: true }, { id: 2, name: "Моссовет", is_active: true }];
    throw new Error(`неожиданный запрос ${path}`);
  });
}

function Where() {
  const l = useLocation();
  return <div data-testid="where">{l.pathname + l.search}</div>;
}

function open(role: string, route = "/dashboards") {
  render(
    <AuthContext.Provider value={{ user: makeUser(role), loading: false, login: async () => undefined, loginWithToken: async () => undefined, logout: () => undefined, refresh: async () => undefined }}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/dashboards" element={<><DashboardsPage /><Where /></>} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

const tabNames = () => Array.from(document.querySelectorAll(".tabs > button")).map((b) => b.textContent);
const apiCalls = (prefix: string) => get.mock.calls.map((c) => String(c[0])).filter((p) => p.startsWith(prefix));

beforeEach(() => {
  get.mockReset();
  download.mockReset();
  download.mockResolvedValue(undefined);
  mockApi();
});

describe("DashboardsPage — вкладки по ролям", () => {
  it("администрация видит все вкладки; число вакантных групп — в названии", async () => {
    open("admin");
    await screen.findByText("СА172");
    await waitFor(() => expect(tabNames()).toContain("Вакантные группы (1)"));
    expect(tabNames().slice(0, 6)).toEqual([
      "День по колледжу", "Свод", "Динамика", "Группа риска", "Дисциплина кураторов", "Вакантные группы (1)",
    ]);
    expect(tabNames()[6]).toMatch(/^Экспорт в Excel/);
  });

  it("зав. отделением и тьютор: «День по отделению»", async () => {
    open("dept_head");
    expect(await screen.findByRole("button", { name: "День по отделению" })).toBeInTheDocument();
  });

  it("соц. педагог и психолог: без «Дисциплины кураторов» и «Вакантных групп»", async () => {
    open("psychologist");
    await screen.findByText("СА172");
    expect(screen.queryByRole("button", { name: "Дисциплина кураторов" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Вакантные группы/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Группа риска" })).toBeInTheDocument();
  });

  it("вкладка из адреса открывается сразу, адрес следует за переключением", async () => {
    const user = userEvent.setup();
    open("admin", "/dashboards?tab=risk");
    expect(await screen.findByRole("link", { name: "Алексеев Пётр" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Динамика" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/dashboards?tab=dynamics"));
  });
});

describe("DashboardsPage — день по колледжу", () => {
  it("показывает группы: ответственный, цифры, процент, статус сдачи", async () => {
    open("admin");
    const row = (await screen.findByText("СА172")).closest("tr") as HTMLElement;
    expect(within(row).getByText("Иванова А.")).toBeInTheDocument();
    expect(within(row).getByText("92.0%")).toBeInTheDocument();
    expect(within(row).getByText("вовремя")).toBeInTheDocument();
    const missing = screen.getByText("ИИ212").closest("tr") as HTMLElement;
    expect(within(missing).getByText("нет куратора")).toBeInTheDocument();
    expect(within(missing).getByText("не сдано")).toBeInTheDocument();
    expect(within(missing).getAllByText("—").length).toBeGreaterThanOrEqual(5); // несданный день — не «100%», а прочерки
    expect(missing).toHaveClass("not-submitted-row");
    expect(within(screen.getByText("ИТ301").closest("tr") as HTMLElement).getByText("задним числом")).toBeInTheDocument();
    expect(apiCalls("/dashboards/day")).toEqual([`/dashboards/day?date=${todayIso()}`]);
  });

  it("фильтр по курсу", async () => {
    const user = userEvent.setup();
    open("admin");
    await screen.findByText("СА172");
    await user.selectOptions(screen.getByDisplayValue("Все курсы"), "2");
    expect(screen.queryByText("СА172")).not.toBeInTheDocument();
    expect(screen.getByText("ИИ212")).toBeInTheDocument();
  });

  it("смена даты перезапрашивает день", async () => {
    const { fireEvent } = await import("@testing-library/react");
    open("admin");
    await screen.findByText("СА172");
    fireEvent.change(document.querySelector('input[type="date"]') as HTMLInputElement, { target: { value: "2026-09-30" } });
    await waitFor(() => expect(apiCalls("/dashboards/day")).toContain("/dashboards/day?date=2026-09-30"));
  });

  it("клик по группе: администрация — в журнал группы на эту дату, специалисты — к списку студентов группы", async () => {
    const user = userEvent.setup();
    open("admin");
    await user.click((await screen.findByText("СА172")).closest("tr") as HTMLElement);
    expect(screen.getByTestId("where")).toHaveTextContent(`/admin?tab=journal&group=1&date=${todayIso()}`);
  });

  it("клик у соц. педагога ведёт к студентам группы", async () => {
    const user = userEvent.setup();
    open("social_pedagogue");
    await user.click((await screen.findByText("СА172")).closest("tr") as HTMLElement);
    expect(screen.getByTestId("where")).toHaveTextContent("/students?group=1");
  });

  it("ошибка загрузки показывается", async () => {
    get.mockImplementation(async (path: string) => {
      if (path.startsWith("/dashboards/day")) throw new ApiError(500, "Сервер недоступен");
      return [];
    });
    open("admin");
    expect(await screen.findByText("Сервер недоступен")).toBeInTheDocument();
  });
});

describe("DashboardsPage — динамика и группа риска", () => {
  it("динамика: среднее по дням с данными, таблица с датами, несданный день — прочерк", async () => {
    const user = userEvent.setup();
    open("admin");
    await screen.findByText("СА172");
    await user.click(screen.getByRole("button", { name: "Динамика" }));
    expect(await screen.findByText("88.0%")).toBeInTheDocument(); // (96 + 80) / 2, день без данных не учитывается
    const row = screen.getByText("01.10.2026").closest("tr") as HTMLElement;
    expect(within(row).getByText("96.0%")).toBeInTheDocument();
    expect(within(screen.getByText("03.10.2026").closest("tr") as HTMLElement).getAllByText("—").length).toBeGreaterThanOrEqual(3);
    expect(apiCalls("/dashboards/dynamics")[0]).toMatch(/date_from=\d{4}-\d{2}-\d{2}&date_to=\d{4}-\d{2}-\d{2}/);
  });

  it("группа риска: ссылка на карточку студента и серия пропусков; пусто — сообщение", async () => {
    const user = userEvent.setup();
    open("admin", "/dashboards?tab=risk");
    const link = await screen.findByRole("link", { name: "Алексеев Пётр" });
    expect(link).toHaveAttribute("href", "/students/7");
    expect(within(link.closest("tr") as HTMLElement).getByText("4")).toBeInTheDocument();

    get.mockImplementation(async (path: string) => (path.startsWith("/dashboards/risk-students") ? [] : GROUPS));
    await user.click(screen.getByRole("button", { name: "День по колледжу" }));
    await user.click(screen.getByRole("button", { name: "Группа риска" }));
    expect(await screen.findByText(/Нет студентов группы риска/)).toBeInTheDocument();
  });
});

describe("DashboardsPage — дисциплина кураторов", () => {
  it("администрация видит таблицу, но строки не кликабельны; зав. отделением — кликабельны и получает разбор по дням", async () => {
    const user = userEvent.setup();
    open("admin", "/dashboards?tab=discipline");
    const row = (await screen.findByText("ИИ212")).closest("tr") as HTMLElement;
    expect(within(row).getByText("4")).toBeInTheDocument();
    expect(row).not.toHaveClass("clickable-row");
    expect(row).toHaveClass("not-submitted-row"); // есть несданные дни
    await user.click(row);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText(/Нажмите на строку/)).not.toBeInTheDocument();
  });

  it("зав. отделением: клик по строке открывает разбор нужной группы", async () => {
    const user = userEvent.setup();
    open("dept_head", "/dashboards?tab=discipline");
    expect(await screen.findByText(/Нажмите на строку/)).toBeInTheDocument();
    await user.click((await screen.findByText("ИИ212")).closest("tr") as HTMLElement);
    const dialog = await screen.findByRole("dialog", { name: "Дисциплина по дням" });
    expect(dialog).toHaveTextContent("группа 2");
    await user.click(within(dialog).getByRole("button", { name: "закрыть разбор" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("DashboardsPage — вакантные группы", () => {
  it("перечисляет только активные группы без куратора; текст не обещает несуществующих рассылок", async () => {
    const user = userEvent.setup();
    open("admin");
    await screen.findByText("СА172");
    await user.click(await screen.findByRole("button", { name: /Вакантные группы/ }));
    const row = screen.getByText("ИИ212", { selector: "td" }).closest("tr") as HTMLElement;
    expect(within(row).getByRole("button", { name: "Назначить куратора" })).toBeInTheDocument();
    expect(screen.queryByText("АРХ-1")).not.toBeInTheDocument(); // архивная группа
    expect(screen.queryByText("СА172", { selector: "td" })).not.toBeInTheDocument(); // у неё куратор есть
    expect(screen.queryByText(/напоминания/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/сводк/i)).not.toBeInTheDocument();
  });

  it("назначение куратора: окно открывается для нужной группы, после сохранения список перезагружается", async () => {
    const user = userEvent.setup();
    const post = vi.mocked(api.post);
    post.mockReset();
    post.mockResolvedValue({});
    open("admin", "/dashboards?tab=vacant");
    const row = (await screen.findByText("ИИ212", { selector: "td" })).closest("tr") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: "Назначить куратора" }));
    const modal = await screen.findByRole("dialog", { name: "Назначить куратора" });
    const loadsBefore = apiCalls("/admin/groups").length;
    await user.click(within(modal).getByRole("button", { name: "Сохранить" }));
    expect(post).toHaveBeenCalledWith("/admin/curator-assignments", expect.objectContaining({ study_group_id: 2, user_id: 11, role_type: "curator" }));
    await waitFor(() => expect(apiCalls("/admin/groups").length).toBe(loadsBefore + 1));
  });

  it("нет вакантных групп — сообщение", async () => {
    get.mockImplementation(async (path: string) => {
      if (path === "/admin/groups") return [GROUPS[0]];
      if (path.startsWith("/dashboards/day")) return DAY;
      return [];
    });
    open("admin", "/dashboards?tab=vacant");
    expect(await screen.findByText(/Вакантных групп нет/)).toBeInTheDocument();
  });
});

describe("DashboardsPage — экспорт и отделение", () => {
  const exportButton = () => screen.getByRole("button", { name: /Экспорт в Excel/ });

  it("экспорт дня берёт выбранный день, не диапазон «Динамики»", async () => {
    const user = userEvent.setup();
    open("admin");
    await screen.findByText("СА172");
    await user.click(exportButton());
    expect(download).toHaveBeenCalledWith(`/export/excel?date_from=${todayIso()}&date_to=${todayIso()}`, `itog_${todayIso()}_${todayIso()}.xlsx`);
  });

  it("у администрации и специалистов есть выбор отделения, он попадает в выгрузку", async () => {
    const user = userEvent.setup();
    open("admin");
    await screen.findByText("СА172");
    await user.selectOptions(await screen.findByTitle("Отделение для свода и экспорта"), "2");
    await user.click(exportButton());
    expect(download.mock.calls[0][0]).toBe(`/export/excel?date_from=${todayIso()}&date_to=${todayIso()}&department_id=2`);
  });

  it("у зав. отделением выбора отделения нет — выгрузка только по своему", async () => {
    const user = userEvent.setup();
    open("dept_head");
    await screen.findByText("СА172");
    expect(screen.queryByTitle("Отделение для свода и экспорта")).not.toBeInTheDocument();
    await user.click(exportButton());
    expect(download.mock.calls[0][0]).not.toContain("department_id");
  });

  it("ошибка скачивания показывается", async () => {
    const user = userEvent.setup();
    download.mockRejectedValue(new ApiError(403, "Нет доступа"));
    open("admin");
    await screen.findByText("СА172");
    await user.click(exportButton());
    expect(await screen.findByText("Нет доступа")).toBeInTheDocument();
  });

  it("вкладка «Свод» получает право фильтровать по отделению только у тех, кому оно положено", async () => {
    const user = userEvent.setup();
    open("admin");
    await screen.findByText("СА172");
    await user.click(screen.getByRole("button", { name: "Свод" }));
    expect(await screen.findByText("свод, фильтр отделения=true")).toBeInTheDocument();
  });
});
