import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { GroupPractice, GroupPractices } from "../api/types";
import { renderPage } from "../test/utils";
import PracticePanel from "./PracticePanel";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});
vi.mock("../utils/feedback", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../utils/feedback")>();
  return { ...actual, dialogs: { ...actual.dialogs, confirm: vi.fn().mockResolvedValue(true) } };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);
const del = vi.mocked(api.delete);

function practice(over: Partial<GroupPractice> = {}): GroupPractice {
  return {
    id: 1, study_group_id: 7, kind: "production", kind_name: "Производственная", date_from: "2026-11-02", date_to: "2026-11-27",
    base: "ООО «Ромашка»", college_supervisor: "Иванова И. И.", base_supervisor: null, phone: null, review_received: false,
    review_received_on: null, note: null, state: "no_review", replaced_marks: 0, ...over,
  };
}

function data(practices: GroupPractice[], canEdit = true): GroupPractices {
  return { group_id: 7, can_edit: canEdit, practices };
}

describe("PracticePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("показывает практику, базу и состояние характеристики", async () => {
    get.mockResolvedValue(data([practice()]));
    renderPage(<PracticePanel groupId={7} />);
    expect(await screen.findByText("ООО «Ромашка»")).toBeInTheDocument();
    expect(screen.getByText("Не получена")).toBeInTheDocument();
    expect(screen.getByText("Нет характеристики")).toBeInTheDocument();
  });

  it("добавляет практику и сообщает, сколько отметок она заменила", async () => {
    get.mockResolvedValue(data([]));
    post.mockResolvedValue(practice({ replaced_marks: 3 }));
    renderPage(<PracticePanel groupId={7} />);
    await userEvent.click(await screen.findByRole("button", { name: "+ Добавить практику" }));
    const dialog = await screen.findByRole("dialog", { name: "Практика группы" });
    const dates = dialog.querySelectorAll<HTMLInputElement>('input[type="date"]');
    await userEvent.type(dates[0], "2026-11-02");
    await userEvent.type(dates[1], "2026-11-27");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/practice/groups/7", expect.objectContaining({ date_from: "2026-11-02", date_to: "2026-11-27", kind: "production" })));
    expect(await screen.findByText(/Отметок, которые она заменила: 3/)).toBeInTheDocument();
  });

  it("удаляет практику после подтверждения", async () => {
    get.mockResolvedValue(data([practice()]));
    del.mockResolvedValue(undefined);
    renderPage(<PracticePanel groupId={7} />);
    await userEvent.click(await screen.findByRole("button", { name: "Удалить практику" }));
    await waitFor(() => expect(del).toHaveBeenCalledWith("/practice/1"));
  });

  it("читающему без права изменения не показывает кнопки", async () => {
    get.mockResolvedValue(data([practice()], false));
    renderPage(<PracticePanel groupId={7} />);
    expect(await screen.findByText("ООО «Ромашка»")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "+ Добавить практику" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Изменить" })).toBeNull();
  });
});
