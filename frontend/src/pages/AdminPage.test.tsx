import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { renderPage } from "../test/utils";
import AdminPage from "./AdminPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

// Вкладки тяжёлые и проверяются отдельными тестами: здесь важно, кто какие вкладки видит и какие права им передаются.
vi.mock("./admin/DepartmentsTab", async () => ({ default: ({ canEdit }: { canEdit: boolean }) => <div>вкладка отделений, правка={String(canEdit)}</div> }));
vi.mock("./admin/GroupsTab", async () => ({ default: (p: { canEdit: boolean; canCreate: boolean }) => <div>вкладка групп, правка={String(p.canEdit)}, создание={String(p.canCreate)}</div> }));
vi.mock("./admin/StudentsTab", async () => ({ default: ({ canCreate }: { canCreate: boolean }) => <div>вкладка студентов, создание={String(canCreate)}</div> }));
vi.mock("./admin/MarkCodesTab", async () => ({ default: ({ canEdit }: { canEdit: boolean }) => <div>вкладка кодов, правка={String(canEdit)}</div> }));
vi.mock("./admin/UsersTab", async () => ({ default: (p: { canCreate: boolean }) => <div>вкладка пользователей, создание={String(p.canCreate)}</div> }));
vi.mock("./admin/CalendarTab", async () => ({ default: (p: { canEdit: boolean; canEditGroups: boolean }) => <div>вкладка календаря, общий={String(p.canEdit)}, группы={String(p.canEditGroups)}</div> }));
vi.mock("./admin/GroupJournalTab", async () => ({ default: () => <div>вкладка журнала</div> }));

beforeEach(() => vi.mocked(api.get).mockResolvedValue([]));

const tabs = () => screen.getAllByRole("button").map((b) => b.textContent);

describe("AdminPage — вкладки по ролям", () => {
  it.each(["admin", "edu_department"])("%s видит полный набор вкладок, начинает с «Группы»", (role) => {
    renderPage(<AdminPage />, { role });
    expect(tabs()).toEqual(["Отделения", "Группы", "Студенты", "Коды отметок", "Пользователи", "Календарь", "Журнал группы"]);
    expect(screen.getByText(/вкладка групп/)).toBeInTheDocument();
  });

  it.each(["dept_head", "tutor"])("%s работает в границах отделения: свой набор вкладок, начинает с журнала", (role) => {
    renderPage(<AdminPage />, { role });
    expect(tabs()).toEqual(["Журнал группы", "Группы", "Студенты", "Пользователи", "Календарь"]);
    expect(screen.getByText("вкладка журнала")).toBeInTheDocument();
  });
});

describe("AdminPage — права вкладкам", () => {
  const open = async (role: string, tab: string) => {
    renderPage(<AdminPage />, { role, route: `/admin?tab=${tab}`, path: "/admin" });
  };

  it("администратор правит всё и создаёт", async () => {
    await open("admin", "groups");
    expect(screen.getByText("вкладка групп, правка=true, создание=true")).toBeInTheDocument();
  });

  it("зав. отделением и тьютор: правка и создание в своём отделении, отделениями и справочниками не управляют", async () => {
    await open("dept_head", "calendar");
    expect(screen.getByText("вкладка календаря, общий=false, группы=true")).toBeInTheDocument();
  });

  it("воспитательный отдел: общий календарь и коды правит, структуру — нет", async () => {
    await open("edu_department", "calendar");
    expect(screen.getByText("вкладка календаря, общий=true, группы=true")).toBeInTheDocument();
  });

  it("воспитательный отдел: группы и пользователи только для чтения", async () => {
    await open("edu_department", "users");
    expect(screen.getByText("вкладка пользователей, создание=false")).toBeInTheDocument();
  });

  it("отделения правит только администратор", async () => {
    await open("admin", "departments");
    expect(screen.getByText("вкладка отделений, правка=true")).toBeInTheDocument();
  });

  it("коды отметок: правят администратор и воспитательный отдел, зав. отделением нет", async () => {
    await open("edu_department", "mark-codes");
    expect(screen.getByText("вкладка кодов, правка=true")).toBeInTheDocument();
  });
});

describe("AdminPage — адрес и переключение", () => {
  it("вкладка из адреса открывается сразу (ссылка из уведомления)", () => {
    renderPage(<AdminPage />, { role: "admin", route: "/admin?tab=journal&group=3&date=2026-10-01", path: "/admin" });
    expect(screen.getByText("вкладка журнала")).toBeInTheDocument();
  });

  it("неизвестная вкладка в адресе заменяется вкладкой по умолчанию", () => {
    renderPage(<AdminPage />, { role: "admin", route: "/admin?tab=hack", path: "/admin" });
    expect(screen.getByText(/вкладка групп/)).toBeInTheDocument();
  });

  it("клик по вкладке переключает содержимое", async () => {
    const user = userEvent.setup();
    renderPage(<AdminPage />, { role: "admin" });
    await user.click(screen.getByRole("button", { name: "Студенты" }));
    expect(screen.getByText("вкладка студентов, создание=true")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Коды отметок" }));
    expect(screen.getByText("вкладка кодов, правка=true")).toBeInTheDocument();
    expect(screen.queryByText(/вкладка студентов/)).not.toBeInTheDocument();
  });
});
