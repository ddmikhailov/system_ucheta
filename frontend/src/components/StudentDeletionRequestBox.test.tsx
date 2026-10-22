import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import StudentDeletionRequestBox from "./StudentDeletionRequestBox";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);

const pending = {
  id: 5, student_id: 10, student_name: "Тест", group_code: "ГД-1", reason: "Ошибка в списке", status: "pending" as const,
  requested_by_name: "Куратор", created_at: "2026-10-21T10:00:00", review_comment: null,
};

describe("StudentDeletionRequestBox", () => {
  beforeEach(() => vi.clearAllMocks());

  it("запрос отправляется с причиной после подтверждения", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue(null);
    post.mockResolvedValue(pending);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<StudentDeletionRequestBox studentId={10} />);
    await user.type(await screen.findByLabelText("Причина"), "Ошибка в списке");
    await user.click(screen.getByRole("button", { name: "Запросить удаление" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/student-deletions", { student_id: 10, reason: "Ошибка в списке" }));
    expect(await screen.findByText(/ждёт решения/)).toBeInTheDocument();
  });

  it("у ждущего запроса — отзыв", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue(pending);
    post.mockResolvedValue({ ...pending, status: "cancelled" });
    render(<StudentDeletionRequestBox studentId={10} />);
    await user.click(await screen.findByRole("button", { name: "Отозвать запрос" }));
    expect(post).toHaveBeenCalledWith("/student-deletions/5/cancel", {});
  });
});
