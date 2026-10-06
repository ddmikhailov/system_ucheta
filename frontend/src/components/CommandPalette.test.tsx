import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { makeUser, renderPage } from "../test/utils";
import CommandPalette from "./CommandPalette";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const SECTIONS = [
  { to: "/dashboards", label: "Витрины" },
  { to: "/students", label: "Студенты" },
];

function Where() {
  const l = useLocation();
  return <div data-testid="where">{l.pathname + l.search}</div>;
}

beforeEach(() => {
  get.mockReset();
  get.mockResolvedValue([{ id: 42, full_name: "Алексеев Пётр", group_code: "СА172", status: "studying" }]);
});

function open(role: string, groups = [] as { id: number; code: string; course: number }[]) {
  const onClose = vi.fn();
  renderPage(
    <>
      <CommandPalette user={makeUser(role, { groups })} sections={SECTIONS} onClose={onClose} />
      <Where />
    </>,
    { role }
  );
  return { onClose, user: userEvent.setup() };
}

describe("CommandPalette", () => {
  it("разделы и админка; фокус в поле; стрелки и Enter открывают выбранное", async () => {
    const { user, onClose } = open("admin");
    const input = screen.getByRole("combobox", { name: "Куда перейти" });
    expect(input).toHaveFocus();
    expect(screen.getByRole("option", { name: /Витрины/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("option", { name: /Пользователи/ })).toBeInTheDocument();
    await user.keyboard("{ArrowDown}");
    expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");
    expect(screen.getAllByRole("option")[1]).toHaveTextContent("Студенты");
    await user.keyboard("{Enter}");
    expect(onClose).toHaveBeenCalled();
    expect(screen.getByTestId("where")).toHaveTextContent("/students");
  });

  it("поиск фильтрует разделы и ищет студентов на сервере", async () => {
    const { user } = open("admin");
    await user.type(screen.getByRole("combobox"), "алекс");
    await waitFor(() => expect(get).toHaveBeenCalledWith("/students?q=%D0%B0%D0%BB%D0%B5%D0%BA%D1%81&limit=8"));
    await user.click(await screen.findByRole("option", { name: /Алексеев Пётр/ }));
    expect(screen.getByTestId("where")).toHaveTextContent("/students/42");
  });

  it("куратор: свои группы ведут в журнал группы, студентов на сервере не ищет", async () => {
    const { user } = open("curator", [{ id: 7, code: "СА172", course: 1 }]);
    await user.type(screen.getByRole("combobox"), "са17");
    await user.click(screen.getByRole("option", { name: /СА172 · 1 курс/ }));
    expect(screen.getByTestId("where")).toHaveTextContent("/cabinet?group=7");
    expect(get).not.toHaveBeenCalled();
    expect(screen.queryByRole("option", { name: /Пользователи/ })).not.toBeInTheDocument();
  });

  it("ничего не найдено — подсказка; Esc закрывает", async () => {
    const { user, onClose } = open("curator");
    await user.type(screen.getByRole("combobox"), "zzzz");
    expect(screen.getByText("Ничего не найдено")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });
});
