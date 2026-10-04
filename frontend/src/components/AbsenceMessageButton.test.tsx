import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { renderPage } from "../test/utils";
import AbsenceMessageButton from "./AbsenceMessageButton";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const TEXT = "Здравствуйте! Пишу вам как куратор группы СА172.\n• 01.10.2026 — Неуважительная причина";

function mockClipboard(write: () => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn(write) }, configurable: true });
  return navigator.clipboard.writeText as ReturnType<typeof vi.fn>;
}

beforeEach(() => {
  get.mockReset();
});

describe("AbsenceMessageButton", () => {
  it("готовит текст, копирует его в буфер и показывает в поле", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue({ days: 14, absences: [{ date: "2026-10-01", code: "н", name: "Неуважительная причина" }], text: TEXT });
    const writeText = mockClipboard(async () => undefined);
    renderPage(<AbsenceMessageButton studentId={5} />, { role: "curator" });
    await user.click(screen.getByRole("button", { name: "Сообщение родителям о пропусках" }));
    expect(get).toHaveBeenCalledWith("/students/5/absence-message?days=14");
    expect(await screen.findByText("Текст скопирован — вставьте его в мессенджер.")).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(TEXT);
    expect(screen.getByLabelText("Текст сообщения родителям")).toHaveValue(TEXT);
  });

  it("буфер недоступен — текст остаётся в поле для ручного копирования", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue({ days: 14, absences: [{ date: "2026-10-01", code: "н", name: "Неуважительная причина" }], text: TEXT });
    mockClipboard(async () => {
      throw new Error("denied");
    });
    renderPage(<AbsenceMessageButton studentId={5} />, { role: "curator" });
    await user.click(screen.getByRole("button", { name: "Сообщение родителям о пропусках" }));
    expect(await screen.findByText(/Не удалось скопировать автоматически/)).toBeInTheDocument();
    expect(screen.getByLabelText("Текст сообщения родителям")).toHaveValue(TEXT);
  });

  it("пропусков нет — сообщать нечего, поля нет", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue({ days: 14, absences: [], text: "" });
    const writeText = mockClipboard(async () => undefined);
    renderPage(<AbsenceMessageButton studentId={5} />, { role: "curator" });
    await user.click(screen.getByRole("button", { name: "Сообщение родителям о пропусках" }));
    expect(await screen.findByText(/нет пропусков без уважительной причины — сообщать нечего/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Текст сообщения родителям")).not.toBeInTheDocument();
    expect(writeText).not.toHaveBeenCalled();
  });

  it("ошибка сервера показана", async () => {
    const user = userEvent.setup();
    get.mockRejectedValue(new ApiError(403, "Нет доступа"));
    renderPage(<AbsenceMessageButton studentId={5} days={30} />, { role: "curator" });
    await user.click(screen.getByRole("button", { name: "Сообщение родителям о пропусках" }));
    expect(await screen.findByText("Нет доступа")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/students/5/absence-message?days=30");
  });
});
