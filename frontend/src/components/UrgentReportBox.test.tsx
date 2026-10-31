import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import UrgentReportBox from "./UrgentReportBox";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);

const sent = {
  id: 3, student_id: 10, student_name: "Тест", group_code: "ГД-1", category: "emergency" as const, text: null,
  author_name: "Куратор", created_at: "2026-10-29T10:00:00", acknowledged_by_name: null, acknowledged_at: null,
};

describe("UrgentReportBox", () => {
  beforeEach(() => vi.clearAllMocks());

  it("сообщение уходит с видом и текстом после подтверждения", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue([]);
    post.mockResolvedValue(sent);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<UrgentReportBox studentId={10} />);
    await user.click(await screen.findByRole("button", { name: "Сообщить заведующему" }));
    await user.selectOptions(screen.getByLabelText("Что случилось"), "emergency");
    await user.type(screen.getByLabelText("Текст сообщения"), "Драка в общежитии");
    await user.click(screen.getByRole("button", { name: "Отправить" }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/urgent-reports", { student_id: 10, category: "emergency", text: "Драка в общежитии" }),
    );
  });

  it("показывает статус приёма и не показывает текст", async () => {
    get.mockResolvedValue([{ ...sent, acknowledged_by_name: "Зав. Отделением", acknowledged_at: "2026-10-29T11:00:00" }]);
    render(<UrgentReportBox studentId={10} />);
    expect(await screen.findByText(/принял\(а\) Зав\. Отделением/)).toBeInTheDocument();
  });
});
