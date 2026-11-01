import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { GroupSubject, GroupSubjects } from "../api/types";
import { dialogs } from "../utils/feedback";
import { renderPage } from "../test/utils";
import TeachersPanel from "./TeachersPanel";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);
const del = vi.mocked(api.delete);

function subject(over: Partial<GroupSubject> = {}): GroupSubject {
  return {
    id: 1, study_group_id: 7, code: "МДК.01.01", name: "Компьютерные сети", teacher_name: "Иванова И. И.",
    teacher_phone: "+7 900 000-00-00", note: null, updated_at: "2030-01-01T00:00:00", ...over,
  };
}

function listing(over: Partial<GroupSubjects> = {}): GroupSubjects {
  return { can_edit: true, subjects: [subject(), subject({ id: 2, code: null, name: "История", teacher_name: "Петров П. П.", teacher_phone: null })], ...over };
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  del.mockReset();
});

describe("TeachersPanel", () => {
  it("показывает дисциплины, преподавателей и ссылку «позвонить»", async () => {
    get.mockResolvedValue(listing());
    renderPage(<TeachersPanel groupId={7} />);
    expect(await screen.findByText("Компьютерные сети")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "+7 900 000-00-00" })).toHaveAttribute("href", "tel:+79000000000");
    expect(screen.getByText("Петров П. П.")).toBeInTheDocument();
  });

  it("ищет по преподавателю", async () => {
    get.mockResolvedValue(listing());
    renderPage(<TeachersPanel groupId={7} />);
    await screen.findByText("История");
    await userEvent.setup().type(screen.getByLabelText("Поиск по дисциплине или преподавателю"), "петров");
    expect(screen.queryByText("Компьютерные сети")).not.toBeInTheDocument();
    expect(screen.getByText("История")).toBeInTheDocument();
  });

  it("добавляет дисциплину", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue(listing({ subjects: [] }));
    post.mockResolvedValue(subject());
    renderPage(<TeachersPanel groupId={7} />);
    await user.click(await screen.findByRole("button", { name: "Добавить дисциплину" }));
    await user.type(screen.getByLabelText("Название дисциплины"), "Физика");
    await user.type(screen.getByLabelText("Телефон преподавателя"), "+7 911");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/groups/7/subjects", {
        code: null, name: "Физика", teacher_name: null, teacher_phone: "+7 911", note: null,
      }),
    );
  });

  it("удаляет дисциплину после подтверждения", async () => {
    const user = userEvent.setup();
    vi.spyOn(dialogs, "confirm").mockResolvedValue(true);
    get.mockResolvedValue(listing());
    del.mockResolvedValue(undefined);
    renderPage(<TeachersPanel groupId={7} />);
    await user.click((await screen.findAllByRole("button", { name: "Удалить" }))[0]);
    await waitFor(() => expect(del).toHaveBeenCalledWith("/groups/7/subjects/1"));
  });

  it("без права правки скрывает кнопки", async () => {
    get.mockResolvedValue(listing({ can_edit: false }));
    renderPage(<TeachersPanel groupId={7} />);
    await screen.findByText("Компьютерные сети");
    expect(screen.queryByRole("button", { name: "Добавить дисциплину" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Изменить" })).not.toBeInTheDocument();
  });
});
