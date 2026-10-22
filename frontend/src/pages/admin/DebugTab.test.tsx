import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { AuditEntry } from "../../api/types";
import { renderPage } from "../../test/utils";
import DebugTab from "./DebugTab";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);

const ENTRIES: AuditEntry[] = [
  { id: 9, created_at: "2026-10-20T09:00:00", user_id: 4, user_name: "Кураторова Ольга", user_role: "curator", action: "mark.update",
    entity_type: "student", entity_id: "15", old_value: "н", new_value: "б", ip_address: "10.0.0.5" },
  { id: 8, created_at: "2026-10-20T08:00:00", user_id: null, user_name: null, user_role: null, action: "group.archive",
    entity_type: "study_group", entity_id: "3", old_value: "active", new_value: null, ip_address: null },
];

beforeEach(() => {
  get.mockReset();
  get.mockImplementation(async (path: string) => {
    if (path === "/admin/users") return [{ id: 4, full_name: "Кураторова Ольга" }];
    if (path.includes("before_id=8")) return { items: [{ ...ENTRIES[1], id: 7, action: "something.new" }], next_before_id: null };
    if (path.includes("user_id=4")) return { items: [ENTRIES[0]], next_before_id: null };
    return { items: ENTRIES, next_before_id: 8 };
  });
});

describe("DebugTab", () => {
  it("при открытии показывает полный журнал: кто, действие, объект, было и стало", async () => {
    renderPage(<DebugTab />);
    const row = (await screen.findByText("Изменил(а) отметку")).closest("tr") as HTMLElement;
    expect(get).toHaveBeenCalledWith("/admin/debug/audit?limit=100");
    expect(within(row).getByRole("link", { name: "Кураторова Ольга" })).toHaveAttribute("href", "/admin/users/4");
    expect(within(row).getByText("· Куратор")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "student №15" })).toHaveAttribute("href", "/students/15");
    expect(within(row).getByText("н")).toBeInTheDocument();
    expect(within(row).getByText("б")).toBeInTheDocument();
    const system = screen.getByText("study_group 3").closest("tr") as HTMLElement;
    expect(within(system).getByText("система")).toBeInTheDocument();
  });

  it("фильтры уходят на сервер по «Показать», «Сбросить» возвращает всё", async () => {
    const user = userEvent.setup();
    renderPage(<DebugTab />);
    await screen.findByText("Изменил(а) отметку");
    await screen.findByRole("option", { name: "Кураторова Ольга" });
    await user.selectOptions(screen.getByLabelText("Кто"), "4");
    await user.selectOptions(screen.getByLabelText("Что"), "mark");
    await user.type(screen.getByLabelText("С"), "2026-10-01");
    await user.click(screen.getByRole("button", { name: "Показать" }));
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith("/admin/debug/audit?limit=100&user_id=4&area=mark&date_from=2026-10-01")
    );
    await waitFor(() => expect(screen.queryByText("study_group 3")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Сбросить" }));
    expect(await screen.findByText("study_group 3")).toBeInTheDocument();
  });

  it("«Показать ещё» догружает старые записи", async () => {
    const user = userEvent.setup();
    renderPage(<DebugTab />);
    await screen.findByText("Изменил(а) отметку");
    await user.click(screen.getByRole("button", { name: "Показать ещё" }));
    expect(await screen.findByText("something.new", { selector: "td" })).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/admin/debug/audit?limit=100&before_id=8");
    expect(screen.queryByRole("button", { name: "Показать ещё" })).not.toBeInTheDocument();
  });
});
