import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { AuthContext } from "../auth/authContextObject";
import type { UserActivityEntry, UserAdmin, UserProfile } from "../api/types";
import { makeUser } from "../test/utils";
import UserProfilePage from "./UserProfilePage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
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

function account(id: number, name: string, over: Partial<UserAdmin> = {}): UserAdmin {
  return {
    id, username: `user${id}`, full_name: name, role: "curator", display_title: null, department_id: 1,
    is_active: true, has_password: true, must_change_password: false, is_locked: false, ...over,
  };
}

function profile(u: UserAdmin, over: Partial<UserProfile> = {}): UserProfile {
  return {
    user: u,
    department_name: "Диджитал",
    created_at: "2026-09-01T07:00:00",
    last_activity_at: "2026-10-05T09:30:00",
    groups: [
      { group_id: 7, group_code: "СА172", course: 1, department_name: "Диджитал", role_type: "curator", start_date: "2026-09-01", end_date: null, is_current: true, students_count: 24 },
      { group_id: 5, group_code: "ИИ111", course: 2, department_name: "Диджитал", role_type: "deputy", start_date: "2025-09-01", end_date: "2026-06-30", is_current: false, students_count: 0 },
    ],
    discipline: { date_from: "2026-09-06", date_to: "2026-10-05", study_days: 20, submitted: 18, on_time: 16, late: 2, missed: 2, percent_on_time: 80 },
    tasks: { total: 5, accepted: 2, submitted: 1, in_work: 1, returned: 1, overdue: 1 },
    marks_created_30d: 31,
    days_submitted_30d: 18,
    notes_written_30d: 4,
    follow_ups_open: 2,
    dossier_views_30d: 9,
    activity_30d: Array.from({ length: 30 }, (_, i) => ({ date: `2026-09-${String(i + 1).padStart(2, "0")}`, count: i % 3 })),
    ...over,
  };
}

const ACTIVITY: UserActivityEntry[] = [
  { id: 30, action: "day.submit", entity_type: "day_submission", entity_id: "11", created_at: "2026-10-05T09:30:00" },
  { id: 29, action: "dossier.note_delete", entity_type: "student", entity_id: "42", created_at: "2026-10-05T08:10:00" },
  { id: 20, action: "something.new", entity_type: "x", entity_id: "1", created_at: "2026-10-01T08:00:00" },
];

let current: UserAdmin;

function Where() {
  const l = useLocation();
  return <div data-testid="where">{l.pathname + l.search + JSON.stringify(l.state ?? null)}</div>;
}

function open({ role = "admin", me = {}, tab, target }: { role?: string; me?: object; tab?: string; target?: UserAdmin } = {}) {
  current = target ?? account(2, "Иванова Анна");
  get.mockImplementation(async (path: string) => {
    if (path === `/admin/users/${current.id}/profile`) return profile(current);
    if (path === "/admin/departments") return DEPARTMENTS;
    if (path.startsWith(`/admin/users/${current.id}/activity`)) {
      if (path.includes("before_id=20")) return { items: [], next_before_id: null };
      if (path.includes("area=day")) return { items: [ACTIVITY[0]], next_before_id: null };
      if (path.includes("before_id=29")) return { items: [ACTIVITY[2]], next_before_id: null };
      return { items: ACTIVITY.slice(0, 2), next_before_id: 29 };
    }
    throw new Error(`неожиданный запрос ${path}`);
  });
  render(
    <AuthContext.Provider value={{ user: makeUser(role, { id: 1, ...me }), loading: false, login: vi.fn(), logout: vi.fn(), refresh: vi.fn() }}>
      <MemoryRouter initialEntries={[`/admin/users/${current.id}${tab ? `?tab=${tab}` : ""}`]}>
        <Routes>
          <Route path="/admin/users/:userId" element={<UserProfilePage />} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
  return userEvent.setup();
}

beforeEach(() => {
  for (const fn of [get, post, patch, del]) fn.mockReset();
});

describe("UserProfilePage — обзор", () => {
  it("шапка: ФИО, роль, отделение, логин, статус и главные цифры", async () => {
    open();
    expect(await screen.findByRole("heading", { name: "Иванова Анна" })).toBeInTheDocument();
    expect(screen.getByText("Куратор")).toBeInTheDocument();
    expect(screen.getByText("логин user2")).toBeInTheDocument();
    expect(screen.getByText("активен")).toBeInTheDocument();
    const onTime = screen.getByText("Дни сданы вовремя").closest(".kpi") as HTMLElement;
    expect(within(onTime).getByText("80%")).toBeInTheDocument();
    expect(within(onTime).getByText("16 из 20 учебных дней")).toBeInTheDocument();
    expect(within(screen.getByText("Задачи просрочены").closest(".kpi") as HTMLElement).getByText("из 5 за 90 дней")).toBeInTheDocument();
  });

  it("обзор: дисциплина, задачи, работа за 30 дней и активность", async () => {
    open();
    await screen.findByRole("heading", { name: "Иванова Анна" });
    expect(screen.getByText(/06\.09\.2026 — 05\.10\.2026/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "вовремя: 16, с опозданием: 2, не сданы: 2" })).toBeInTheDocument();
    const work = screen.getByRole("heading", { name: "Работа за 30 дней" }).closest("section") as HTMLElement;
    expect(within(work).getByText("Отметок поставлено").nextSibling).toHaveTextContent("31");
    expect(within(work).getByText("Просмотров досье").nextSibling).toHaveTextContent("9");
    expect(screen.getByText(/за 30 дней, активных/)).toHaveTextContent("30 действий за 30 дней, активных — 20 дней.");
  });

  it("группы: текущие и прошлые закрепления со ссылкой на журнал группы", async () => {
    const u = open();
    await u.click(await screen.findByRole("tab", { name: /Группы/ }));
    const now = screen.getByText("СА172").closest("tr") as HTMLElement;
    expect(within(now).getByText("Куратор")).toBeInTheDocument();
    expect(within(now).getByText("24")).toBeInTheDocument();
    expect(within(now).getByText(/с 01\.09\.2026 · сейчас/)).toBeInTheDocument();
    expect(within(now).getByRole("link", { name: "Открыть" })).toHaveAttribute("href", "/admin?tab=journal&group=7");
    const old = screen.getByText("ИИ111").closest("tr") as HTMLElement;
    expect(old).toHaveClass("row-muted");
    expect(within(old).getByText("Заместитель")).toBeInTheDocument();
    expect(within(old).getByText(/по 30\.06\.2026/)).toBeInTheDocument();
  });

  it("ошибка (чужое отделение) — сообщение сервера и ссылка назад", async () => {
    get.mockRejectedValue(new ApiError(403, "Пользователь не относится к вашему отделению"));
    render(
      <AuthContext.Provider value={{ user: makeUser("dept_head"), loading: false, login: vi.fn(), logout: vi.fn(), refresh: vi.fn() }}>
        <MemoryRouter initialEntries={["/admin/users/5"]}>
          <Routes><Route path="/admin/users/:userId" element={<UserProfilePage />} /></Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    );
    expect(await screen.findByText("Пользователь не относится к вашему отделению")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← К пользователям" })).toHaveAttribute("href", "/admin?tab=users");
  });

  it("воспитательный отдел смотрит, но вкладки «Управление» нет", async () => {
    open({ role: "edu_department" });
    await screen.findByRole("heading", { name: "Иванова Анна" });
    expect(screen.queryByRole("tab", { name: "Управление" })).not.toBeInTheDocument();
    expect(get).not.toHaveBeenCalledWith("/admin/departments");
  });
});

describe("UserProfilePage — действия", () => {
  it("лента по дням со временем и подписями; «Показать ещё» догружает старые", async () => {
    const u = open({ tab: "activity" });
    expect(await screen.findByText("Сдал(а) день")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/admin/users/2/activity?limit=50");
    const note = screen.getByText(/Удалил\(а\) запись индивидуальной работы/).closest("li") as HTMLElement;
    expect(within(note).getByRole("link", { name: "открыть" })).toHaveAttribute("href", "/students/42");
    expect(note.querySelector("time")).toHaveAttribute("dateTime", "2026-10-05T08:10:00");

    await u.click(screen.getByRole("button", { name: "Показать ещё" }));
    expect(await screen.findByText("something.new")).toBeInTheDocument(); // неизвестное действие — кодом
    expect(get).toHaveBeenCalledWith("/admin/users/2/activity?limit=50&before_id=29");
    expect(screen.queryByRole("button", { name: "Показать ещё" })).not.toBeInTheDocument();
  });

  it("фильтр по области уходит на сервер", async () => {
    const u = open({ tab: "activity" });
    await screen.findByText("Сдал(а) день");
    await u.selectOptions(screen.getByLabelText("Что показать"), "day");
    await waitFor(() => expect(get).toHaveBeenCalledWith("/admin/users/2/activity?limit=50&area=day"));
    await waitFor(() => expect(screen.queryByText(/Удалил\(а\) запись/)).not.toBeInTheDocument());
  });
});

describe("UserProfilePage — управление учётной записью", () => {
  async function manage(opts: Parameters<typeof open>[0] = {}) {
    const u = open({ tab: "manage", ...opts });
    await screen.findByText("Учётная запись");
    return u;
  }

  it("сохраняет ФИО, логин, роль и отделение", async () => {
    const u = await manage();
    patch.mockResolvedValue({});
    const name = screen.getByDisplayValue("Иванова Анна");
    await u.clear(name);
    await u.type(name, "Иванова Анна Петровна");
    await u.selectOptions(screen.getAllByRole("combobox")[0], "deputy_curator");
    await u.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(patch).toHaveBeenCalledWith("/admin/users/2", {
      username: "user2", full_name: "Иванова Анна Петровна", role: "deputy_curator", department_id: 1,
    });
    expect(await screen.findByText("Сохранено")).toBeInTheDocument();
  });

  it("свою роль и отделение менять нельзя: поле роли заблокировано, в запросе их нет", async () => {
    const u = await manage({ target: account(1, "Админов Админ", { role: "admin", department_id: null }) });
    patch.mockResolvedValue({});
    expect(screen.getByDisplayValue("Администратор")).toBeDisabled();
    await u.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(patch).toHaveBeenCalledWith("/admin/users/1", { username: "user1", full_name: "Админов Админ" });
    expect(screen.queryByRole("button", { name: "В архив" })).not.toBeInTheDocument(); // себя в архив нельзя
  });

  it("сброс пароля показывает новый пароль; для пользователя без пароля кнопка называется «Выдать пароль»", async () => {
    const u = await manage({ target: account(2, "Иванова Анна", { has_password: false }) });
    post.mockResolvedValue({ username: "user2", password: "Gen-Pass-777" });
    await u.click(screen.getByRole("button", { name: "Выдать пароль" }));
    expect(post).toHaveBeenCalledWith("/admin/users/2/set-password", {});
    expect(await screen.findByText("Gen-Pass-777")).toBeInTheDocument();
  });

  it("свой пароль: короче 10 символов не отправляется, подходящий уходит в запрос", async () => {
    const u = await manage();
    await u.click(screen.getByRole("button", { name: "Задать свой пароль" }));
    const input = screen.getByPlaceholderText("Свой пароль");
    expect(input).toHaveAttribute("minlength", "10"); // как на сервере
    await u.type(input, "ninechars");
    await u.click(screen.getByRole("button", { name: "Задать" }));
    expect(post).not.toHaveBeenCalled();

    post.mockResolvedValue({ username: "user2", password: "LongEnough1!" });
    await u.clear(input);
    await u.type(input, "LongEnough1!");
    await u.click(screen.getByRole("button", { name: "Задать" }));
    expect(post).toHaveBeenCalledWith("/admin/users/2/set-password", { password: "LongEnough1!" });
    expect(await screen.findByText("LongEnough1!")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Свой пароль")).not.toBeInTheDocument();
  });

  it("слабый пароль — сообщение сервера", async () => {
    const u = await manage();
    await u.click(screen.getByRole("button", { name: "Задать свой пароль" }));
    post.mockRejectedValue(new ApiError(400, "Пароль слишком простой"));
    await u.type(screen.getByPlaceholderText("Свой пароль"), "password123");
    await u.click(screen.getByRole("button", { name: "Задать" }));
    expect(await screen.findByText("Пароль слишком простой")).toBeInTheDocument();
  });

  it("«Разблокировать» есть только у заблокированного", async () => {
    const u = await manage({ target: account(2, "Иванова Анна", { is_locked: true }) });
    post.mockResolvedValue({});
    await u.click(screen.getByRole("button", { name: "Разблокировать" }));
    expect(post).toHaveBeenCalledWith("/admin/users/2/unlock");
  });

  it("у незаблокированного «Разблокировать» нет", async () => {
    await manage();
    expect(screen.queryByRole("button", { name: "Разблокировать" })).not.toBeInTheDocument();
  });

  it("архивация остаётся на странице и сообщает итог; «Удалить насовсем» есть только у архивного", async () => {
    const u = await manage();
    patch.mockResolvedValue({});
    expect(screen.queryByRole("button", { name: "Удалить насовсем" })).not.toBeInTheDocument();
    await u.click(screen.getByRole("button", { name: "В архив" }));
    expect(patch).toHaveBeenCalledWith("/admin/users/2", { is_active: false });
    expect(await screen.findByText("Пользователь перенесён в архив")).toBeInTheDocument();
    expect(get.mock.calls.filter(([p]) => p === "/admin/users/2/profile").length).toBe(2); // профиль перечитан
  });

  it("удаление спрашивает подтверждение и возвращает к списку с итогом", async () => {
    const u = await manage({ target: account(5, "Архивов Артём", { is_active: false }) });
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    await u.click(screen.getByRole("button", { name: "Удалить насовсем" }));
    expect(del).not.toHaveBeenCalled();

    confirm.mockReturnValueOnce(true);
    del.mockResolvedValue({ deleted: false, anonymized: true, detail: "Есть история действий — данные обезличены" });
    await u.click(screen.getByRole("button", { name: "Удалить насовсем" }));
    expect(del).toHaveBeenCalledWith("/admin/users/5");
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/admin?tab=users"));
    expect(screen.getByTestId("where")).toHaveTextContent("данные обезличены");
  });

  it("зав. отделением не меняет отделение пользователя (поля нет)", async () => {
    await manage({ role: "dept_head", me: { id: 99, department_name: "Диджитал" } });
    expect(screen.queryByText("Отделение", { selector: "label" })).not.toBeInTheDocument();
  });
});
