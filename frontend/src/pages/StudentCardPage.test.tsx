import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { AuthContext } from "../auth/authContextObject";
import type { StudentCard } from "../api/types";
import { makeUser } from "../test/utils";
import { todayIso } from "../utils/date";
import StudentCardPage from "./StudentCardPage";
import { chooseOption } from "../test/searchSelect";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});
// Досье и помесячная посещаемость — отдельные компоненты со своими тестами.
vi.mock("../hooks/useDossier", async () => ({
  useDossier: () => ({
    dossier: { student_id: 10, profile: {}, special: null, special_available: true, guardians: [{ id: 1 }, { id: 2 }], notes: [
      { id: 1, follow_up_on: "2026-10-10", follow_up_done: false }, { id: 2, follow_up_on: null, follow_up_done: false },
    ] },
    error: null, notice: null, setDossier: vi.fn(), setError: vi.fn(), setNotice: vi.fn(), load: vi.fn(),
  }),
}));
vi.mock("../components/StudentDossier", async () => ({
  DossierSection: (p: { studentId: number; isAdmin: boolean; section: string }) => (
    <div>досье {p.studentId}, раздел {p.section}, журнал просмотров={String(p.isAdmin)}</div>
  ),
}));
vi.mock("../components/StudentMonthAttendance", async () => ({ default: () => <div>посещаемость по месяцам</div> }));

const get = vi.mocked(api.get);
const patch = vi.mocked(api.patch);
const del = vi.mocked(api.delete);

function card(over: Partial<StudentCard> = {}): StudentCard {
  return {
    id: 10, full_name: "Алексеев Пётр Андреевич", last_name: "Алексеев", first_name: "Пётр", middle_name: "Андреевич",
    status: "studying", enrolled_at: "2026-09-01", left_at: null,
    group: { id: 7, code: "СА172", course: 1, study_form: "очная", is_active: true, department_id: 1, department_name: "Диджитал" },
    curator_name: "Иванова А.", deputy_name: null,
    group_history: [
      { group_id: 5, group_code: "ИИ111", start_date: "2026-09-01", end_date: "2026-09-15" },
      { group_id: 7, group_code: "СА172", start_date: "2026-09-16", end_date: null },
    ],
    stats: { date_from: "2026-09-05", date_to: "2026-10-04", in_list: 20, present: 17, absent_total: 3, absent_excused: 2, absent_unexcused: 1, late: 1, percent: 85, by_code: { н: 1, б: 2 } },
    recent_marks: [{ date: "2026-10-01", code: "н", name: "Неуважительная причина", comment: "Не предупредил", basis_reference: null }],
    ...over,
  };
}

const GROUPS = [
  { id: 7, code: "СА172", course: 1, is_active: true },
  { id: 8, code: "ИИ112", course: 2, is_active: true },
  { id: 9, code: "АРХ-1", course: 3, is_active: false },
];

function Where() {
  const l = useLocation();
  return <div data-testid="where">{l.pathname + l.search + JSON.stringify(l.state ?? null)}</div>;
}

function open(role: string, c: StudentCard = card(), tab?: string) {
  get.mockImplementation(async (path: string) => {
    if (path === "/students/10") return c;
    if (path === "/admin/groups") return GROUPS;
    throw new Error(`неожиданный запрос ${path}`);
  });
  render(
    <AuthContext.Provider value={{ user: makeUser(role), loading: false, login: vi.fn(), loginWithToken: vi.fn(), logout: vi.fn(), refresh: vi.fn() }}>
      <MemoryRouter initialEntries={[tab ? `/students/10?tab=${tab}` : "/students/10"]}>
        <Routes>
          <Route path="/students/:studentId" element={<StudentCardPage />} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

beforeEach(() => {
  for (const fn of [get, patch, del]) fn.mockReset();
});

describe("StudentCardPage — просмотр", () => {
  it("показывает данные студента, куратора, даты в формате ДД.ММ.ГГГГ, статистику, отметки и историю групп", async () => {
    const user = userEvent.setup();
    open("admin");
    expect(await screen.findByRole("heading", { name: "Алексеев Пётр Андреевич" })).toBeInTheDocument();
    expect(screen.getAllByText("СА172 · 1 курс").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Иванова А.")).toBeInTheDocument();
    expect(screen.getByText("нет")).toBeInTheDocument(); // заместителя нет
    const enrolled = screen.getByText("Дата зачисления").closest("div") as HTMLElement;
    expect(within(enrolled).getByText("01.09.2026")).toBeInTheDocument();
    expect(screen.getByText("85%")).toBeInTheDocument(); // в шапке — главные цифры

    await user.click(screen.getByRole("tab", { name: "Посещаемость" }));
    expect(screen.getByText(/05\.09\.2026 — 04\.10\.2026/)).toBeInTheDocument();
    expect(screen.getByText("3 (уваж. 2, неуваж. 1)")).toBeInTheDocument();
    const mark = screen.getByText("Не предупредил").closest("tr") as HTMLElement;
    expect(within(mark).getByText("01.10.2026")).toBeInTheDocument();
    expect(screen.getByText("посещаемость по месяцам")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "История" }));
    const old = screen.getByText("ИИ111", { selector: "td" }).closest("tr") as HTMLElement; // история групп
    expect(within(old).getByText("15.09.2026")).toBeInTheDocument();
    expect(within(screen.getByText("по настоящее время").closest("tr") as HTMLElement).getByText("16.09.2026")).toBeInTheDocument();
  });

  it("вкладки: досье, представители и индивидуальная работа — отдельно, с числом записей; вкладка в адресе", async () => {
    const user = userEvent.setup();
    open("curator");
    const tablist = await screen.findByRole("tablist", { name: "Разделы карточки студента" });
    expect(within(tablist).getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "Обзор", "Досье", "Представители2", "Индивидуальная работа2", "Посещаемость", "История",
    ]);
    expect(screen.getByRole("tab", { name: "Обзор" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByText(/раздел profile/)).not.toBeInTheDocument(); // неоткрытая вкладка не рисуется

    await user.click(screen.getByRole("tab", { name: /Представители/ }));
    expect(screen.getByText("досье 10, раздел guardians, журнал просмотров=false")).toBeVisible();
    await user.click(screen.getByRole("tab", { name: /Индивидуальная работа/ }));
    expect(screen.getByText("досье 10, раздел notes, журнал просмотров=false")).toBeVisible();
    // Открытая раньше вкладка остаётся в документе (ввод не теряется), но скрыта.
    expect(screen.getByText(/раздел guardians/).closest("[role=tabpanel]")).toHaveAttribute("hidden");

    // Стрелки переключают вкладки, как в обычном списке вкладок.
    screen.getByRole("tab", { name: /Индивидуальная работа/ }).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Посещаемость" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "Посещаемость" })).toHaveAttribute("aria-selected", "true");
  });

  it("открывается сразу на вкладке из адреса; в шапке — число вопросов, к которым надо вернуться", async () => {
    open("admin", card(), "dossier");
    expect(await screen.findByText("досье 10, раздел profile, журнал просмотров=true")).toBeInTheDocument();
    const followUps = screen.getByText("Вернуться к вопросу").closest(".kpi") as HTMLElement;
    expect(within(followUps).getByText("1")).toBeInTheDocument();
  });

  it("в карточке есть кнопка «Сообщение родителям о пропусках» — она запрашивает текст по этому студенту", async () => {
    const user = userEvent.setup();
    open("curator");
    const button = await screen.findByRole("button", { name: "Сообщение родителям о пропусках" });
    get.mockImplementation(async (path: string) => {
      if (path === "/students/10/absence-message?days=14") return { days: 14, absences: [], text: "" };
      throw new Error(`неожиданный запрос ${path}`);
    });
    await user.click(button);
    expect(await screen.findByText(/сообщать нечего/)).toBeInTheDocument();
  });

  it("нет сданных дней — пояснение вместо цифр; нет отметок — тоже", async () => {
    open("admin", card({ stats: { ...card().stats, in_list: 0 }, recent_marks: [] }), "attendance");
    expect(await screen.findByText(/нет сданных дней по группе/)).toBeInTheDocument();
    expect(screen.getByText("Отметок пока нет.")).toBeInTheDocument();
  });

  it("не учащийся помечен заметным статусом", async () => {
    open("admin", card({ status: "expelled", left_at: "2026-09-25" }));
    await screen.findByRole("heading", { name: "Алексеев Пётр Андреевич" });
    expect(screen.getAllByText("Отчислен").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("25.09.2026")).toBeInTheDocument();
    expect(document.querySelector(".profile-hero .risk-badge")).not.toBeNull();
  });

  it("журнал просмотров досье доступен только администратору и тьютору", async () => {
    open("tutor", card(), "history");
    expect(await screen.findByText("досье 10, раздел log, журнал просмотров=true")).toBeInTheDocument();
  });

  it("ошибка загрузки (чужая группа) показывается вместо карточки", async () => {
    get.mockRejectedValue(new ApiError(403, "Это не ваша группа"));
    render(
      <AuthContext.Provider value={{ user: makeUser("curator"), loading: false, login: vi.fn(), loginWithToken: vi.fn(), logout: vi.fn(), refresh: vi.fn() }}>
        <MemoryRouter initialEntries={["/students/10"]}>
          <Routes><Route path="/students/:studentId" element={<StudentCardPage />} /></Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    );
    expect(await screen.findByText("Это не ваша группа")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← К моим группам" })).toHaveAttribute("href", "/cabinet");
  });
});

describe("StudentCardPage — ссылка «назад» по роли", () => {
  it.each([
    // Куратор возвращается к списку своей группы.
    ["curator", "← К группе СА172", "/cabinet/groups/7?tab=students"],
    ["deputy_curator", "← К группе СА172", "/cabinet/groups/7?tab=students"],
    ["psychologist", "← К поиску студентов", "/students"],
    ["social_pedagogue", "← К поиску студентов", "/students"],
    ["admin", "← К списку студентов", "/admin?tab=students"],
    ["dept_head", "← К списку студентов", "/admin?tab=students"],
  ])("%s", async (role, label, href) => {
    open(role);
    expect(await screen.findByRole("link", { name: label })).toHaveAttribute("href", href);
  });
});

describe("StudentCardPage — управление", () => {
  it.each(["curator", "deputy_curator", "psychologist", "social_pedagogue", "edu_department"])(
    "%s: карточка только для чтения, блока «Управление» нет",
    async (role) => {
      open(role);
      await screen.findByRole("heading", { name: "Алексеев Пётр Андреевич" });
      expect(screen.queryByRole("tab", { name: "Управление" })).not.toBeInTheDocument();
      expect(get).not.toHaveBeenCalledWith("/admin/groups");
    }
  );

  it.each(["admin", "tutor", "dept_head"])("%s видит «Управление»", async (role) => {
    open(role);
    expect(await screen.findByRole("tab", { name: "Управление" })).toBeInTheDocument();
  });

  it("правка ФИО без перевода: отправляются части ФИО и текущая группа", async () => {
    const user = userEvent.setup();
    open("admin", card(), "manage");
    patch.mockResolvedValue({});
    await screen.findByRole("button", { name: "Применить" });
    const last = screen.getByPlaceholderText("Фамилия");
    await user.clear(last);
    await user.type(last, "Алексеев-Смирнов");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(patch).toHaveBeenCalledWith("/admin/students/10", {
      last_name: "Алексеев-Смирнов", first_name: "Пётр", middle_name: "Андреевич", study_group_id: 7,
    });
    expect(await screen.findByText("Данные студента сохранены")).toBeInTheDocument();
  });

  it("перевод в другую группу: предупреждение с кодом группы, отказ ничего не отправляет", async () => {
    const user = userEvent.setup();
    open("admin", card(), "manage");
    await screen.findByRole("button", { name: "Применить" });
    await chooseOption(user, screen.getByRole("combobox", { name: "Группа" }), "ИИ112");
    expect(screen.getByText(/будет выполнен перевод с сегодняшнего дня/)).toBeInTheDocument();
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("«ИИ112»"));
    expect(patch).not.toHaveBeenCalled();

    confirm.mockReturnValueOnce(true);
    patch.mockResolvedValue({});
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(patch).toHaveBeenCalledWith("/admin/students/10", expect.objectContaining({ study_group_id: 8 }));
  });

  it("список групп для перевода — только активные; текущая группа есть всегда", async () => {
    const user = userEvent.setup();
    open("admin", card(), "manage");
    await screen.findByRole("button", { name: "Применить" });
    const box = screen.getByRole("combobox", { name: "Группа" });
    await user.click(box);
    const listbox = screen.getByRole("listbox");
    expect(within(listbox).getAllByRole("option")).toHaveLength(2);
    expect(within(listbox).queryByRole("option", { name: "АРХ-1" })).not.toBeInTheDocument();
  });

  it("смена статуса: подтверждение, дата выбытия только для не «Учится»", async () => {
    const user = userEvent.setup();
    open("admin", card(), "manage");
    patch.mockResolvedValue({});
    await screen.findByRole("button", { name: "Применить" });
    expect(screen.queryByText("Дата выбытия", { selector: "label" })).not.toBeInTheDocument();
    const statusSelect = screen.getAllByRole("combobox")[1];
    await user.selectOptions(statusSelect, "expelled");
    const apply = screen.getByRole("button", { name: "Применить" });
    expect(screen.getByLabelText("Дата выбытия")).toHaveValue(todayIso());

    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    await user.click(apply);
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("«Отчислен»"));
    expect(patch).not.toHaveBeenCalled();

    confirm.mockReturnValueOnce(true);
    await user.click(apply);
    expect(patch).toHaveBeenCalledWith("/admin/students/10/status", { status: "expelled", left_at: todayIso() });
    expect(await screen.findByText("Статус обучения изменён")).toBeInTheDocument();
  });

  it("«Применить» недоступна, пока статус не изменён", async () => {
    open("admin", card(), "manage");
    await screen.findByRole("button", { name: "Применить" });
    expect(screen.getByRole("button", { name: "Применить" })).toBeDisabled();
  });

  it("учащегося удалить нельзя — подсказка вместо кнопки", async () => {
    open("admin", card(), "manage");
    await screen.findByRole("button", { name: "Применить" });
    expect(screen.getByText(/Удалить студента можно только после перевода в академ/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Удалить студента насовсем" })).not.toBeInTheDocument();
  });

  it("отчисленного можно удалить: подтверждение, затем переход к списку с итогом операции", async () => {
    const user = userEvent.setup();
    open("admin", card({ status: "expelled", left_at: "2026-09-25" }), "manage");
    del.mockResolvedValue({ deleted: false, anonymized: true, detail: "Есть история посещаемости — данные обезличены" });
    const button = await screen.findByRole("button", { name: "Удалить студента насовсем" });
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    await user.click(button);
    expect(del).not.toHaveBeenCalled();
    confirm.mockReturnValueOnce(true);
    await user.click(button);
    expect(del).toHaveBeenCalledWith("/admin/students/10");
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent('/admin?tab=students'));
    expect(screen.getByTestId("where")).toHaveTextContent("данные обезличены"); // итог передан вкладке «Студенты»
  });

  it("ошибки сохранения и удаления показываются, кнопки остаются доступны", async () => {
    const user = userEvent.setup();
    open("dept_head", card({ status: "academic_leave", left_at: "2026-09-20" }), "manage");
    patch.mockRejectedValue(new ApiError(403, "Студент не из вашего отделения"));
    await screen.findByRole("button", { name: "Применить" });
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(await screen.findByText("Студент не из вашего отделения")).toBeInTheDocument();

    vi.spyOn(window, "confirm").mockReturnValue(true);
    del.mockRejectedValue(new ApiError(403, "Нет прав"));
    await user.click(screen.getByRole("button", { name: "Удалить студента насовсем" }));
    expect(await screen.findByText("Нет прав")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Удалить студента насовсем" })).toBeEnabled();
  });
});
