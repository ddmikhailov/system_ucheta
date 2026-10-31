import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { CurrentPracticeRow } from "../../api/types";
import { renderPage } from "../../test/utils";
import PracticeTab from "./PracticeTab";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);

function row(over: Partial<CurrentPracticeRow>): CurrentPracticeRow {
  return {
    id: 1, study_group_id: 7, group_code: "СА172", course: 2, department: "Диджитал", kind_name: "Производственная",
    date_from: "2026-11-02", date_to: "2026-11-27", base: "ООО «Ромашка»", college_supervisor: null, base_supervisor: null,
    phone: null, review_received: false, state: "active", ...over,
  };
}

describe("PracticeTab", () => {
  beforeEach(() => vi.clearAllMocks());

  it("показывает группы на практике и фильтр «без характеристики»", async () => {
    get.mockResolvedValue([row({}), row({ id: 2, group_code: "ИС201", state: "no_review" })]);
    renderPage(<PracticeTab deptQuery="" reloadKey={0} />);
    expect(await screen.findByText("СА172")).toBeInTheDocument();
    expect(screen.getByText("Идёт сейчас")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: /Только без характеристики/ }));
    expect(screen.queryByText("СА172")).toBeNull();
    expect(screen.getByText("ИС201")).toBeInTheDocument();
  });

  it("передаёт отделение в запросе", async () => {
    get.mockResolvedValue([]);
    renderPage(<PracticeTab deptQuery="&department_id=3" reloadKey={0} />);
    expect(await screen.findByText(/Сейчас нет групп на практике/)).toBeInTheDocument();
    expect(get.mock.calls[0][0]).toBe("/practice/current?department_id=3");
  });
});
