import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import UrgentReportInbox from "./UrgentReportInbox";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);

const report = {
  id: 3, student_id: 10, student_name: "Тест Студент", group_code: "ГД-1", category: "offense" as const, text: "Задержан полицией",
  author_name: "Куратор", created_at: "2026-10-29T10:00:00", acknowledged_by_name: null, acknowledged_at: null,
};

describe("UrgentReportInbox", () => {
  beforeEach(() => vi.clearAllMocks());

  it("без сообщений блока нет", async () => {
    get.mockResolvedValue([]);
    const { container } = render(<MemoryRouter><UrgentReportInbox /></MemoryRouter>);
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("показывает текст и принимает сообщение", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue([report]);
    post.mockResolvedValue({ ...report });
    render(<MemoryRouter><UrgentReportInbox /></MemoryRouter>);
    expect(await screen.findByText("Задержан полицией")).toBeInTheDocument();
    get.mockResolvedValue([]);
    await user.click(screen.getByRole("button", { name: "Принято" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/urgent-reports/3/acknowledge", {}));
  });
});
