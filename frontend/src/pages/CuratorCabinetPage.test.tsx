import { screen } from "@testing-library/react";
import { Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { renderPage } from "../test/utils";
import CuratorCabinetPage from "./CuratorCabinetPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);

function Where() {
  const l = useLocation();
  return <div data-testid="where">{l.pathname + l.search}</div>;
}

function open(route = "/cabinet") {
  renderPage(
    <Routes>
      <Route path="/cabinet" element={<CuratorCabinetPage />} />
      <Route path="*" element={<Where />} />
    </Routes>,
    { role: "curator", route }
  );
}

const group = (id: number, code: string, over = {}) => ({
  id, code, course: 2, is_submitted_today: false, students_count: 25, risk_count: 0, role_type: "curator", ...over,
});

beforeEach(() => get.mockReset());

describe("CuratorCabinetPage — «Мои группы»", () => {
  it("карточки групп: курс, роль, студенты, группа риска, сдан ли сегодня; ведут на страницу группы", async () => {
    get.mockResolvedValue([group(7, "СА172", { is_submitted_today: true }), group(8, "ИИ212", { risk_count: 3, role_type: "deputy" })]);
    open();
    const first = await screen.findByRole("link", { name: /СА172/ });
    expect(first).toHaveAttribute("href", "/cabinet/groups/7");
    expect(first).toHaveTextContent("Сегодня сдано");
    const second = screen.getByRole("link", { name: /ИИ212/ });
    expect(second).toHaveTextContent("заместитель куратора");
    expect(second).toHaveTextContent("в группе риска: 3");
    expect(second).toHaveTextContent("25 студентов");
    expect(second).toHaveTextContent("Сегодня не сдано");
  });

  it("одна группа — сразу её страница", async () => {
    get.mockResolvedValue([group(7, "СА172")]);
    open();
    expect(await screen.findByTestId("where")).toHaveTextContent("/cabinet/groups/7");
  });

  it("старые ссылки из уведомлений (?group=&date=) ведут в журнал группы на этот день", async () => {
    open("/cabinet?group=7&date=2026-10-02");
    expect(await screen.findByTestId("where")).toHaveTextContent("/cabinet/groups/7?date=2026-10-02");
    expect(get).not.toHaveBeenCalled();
  });

  it("нет закреплённых групп — подсказка", async () => {
    get.mockResolvedValue([]);
    open();
    expect(await screen.findByText("У вас нет закреплённых групп.")).toBeInTheDocument();
  });
});
