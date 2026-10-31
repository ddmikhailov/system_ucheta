import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { renderPage } from "../test/utils";
import ParentMessageButton from "./ParentMessageButton";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const TEXT = "Здравствуйте! Пишу вам как куратор группы СА172.\n• 01.10.2026";
const PREPARE = { name: "Подготовить сообщение" };

function mockClipboard(write: () => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn(write) }, configurable: true });
  return navigator.clipboard.writeText as ReturnType<typeof vi.fn>;
}

beforeEach(() => {
  get.mockReset();
});

describe("ParentMessageButton", () => {
  it("готовит текст, копирует его в буфер и показывает в поле", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue({ kind: "absences", text: TEXT, empty_reason: null });
    const writeText = mockClipboard(async () => undefined);
    renderPage(<ParentMessageButton studentId={5} />, { role: "curator" });
    await user.click(screen.getByRole("button", PREPARE));
    expect(get).toHaveBeenCalledWith("/students/5/parent-message?kind=absences&days=14");
    expect(await screen.findByText("Текст скопирован — вставьте его в мессенджер.")).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(TEXT);
    expect(screen.getByLabelText("Текст сообщения родителям")).toHaveValue(TEXT);
  });

  it("выбранный вид сообщения уходит в запрос", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue({ kind: "late", text: TEXT, empty_reason: null });
    mockClipboard(async () => undefined);
    renderPage(<ParentMessageButton studentId={5} />, { role: "curator" });
    await user.selectOptions(screen.getByLabelText("Вид сообщения родителям"), "late");
    await user.click(screen.getByRole("button", PREPARE));
    expect(get).toHaveBeenCalledWith("/students/5/parent-message?kind=late&days=14");
  });

  it("буфер недоступен — текст остаётся в поле для ручного копирования", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue({ kind: "absences", text: TEXT, empty_reason: null });
    mockClipboard(async () => {
      throw new Error("denied");
    });
    renderPage(<ParentMessageButton studentId={5} />, { role: "curator" });
    await user.click(screen.getByRole("button", PREPARE));
    expect(await screen.findByText(/Не удалось скопировать автоматически/)).toBeInTheDocument();
    expect(screen.getByLabelText("Текст сообщения родителям")).toHaveValue(TEXT);
  });

  it("сообщать нечего — показана причина, поля нет", async () => {
    const user = userEvent.setup();
    get.mockResolvedValue({ kind: "late", text: "", empty_reason: "За последние 14 дн. нет опозданий — сообщать нечего." });
    const writeText = mockClipboard(async () => undefined);
    renderPage(<ParentMessageButton studentId={5} />, { role: "curator" });
    await user.click(screen.getByRole("button", PREPARE));
    expect(await screen.findByText(/нет опозданий — сообщать нечего/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Текст сообщения родителям")).not.toBeInTheDocument();
    expect(writeText).not.toHaveBeenCalled();
  });

  it("ошибка сервера показана", async () => {
    const user = userEvent.setup();
    get.mockRejectedValue(new ApiError(403, "Нет доступа"));
    renderPage(<ParentMessageButton studentId={5} days={30} />, { role: "curator" });
    await user.click(screen.getByRole("button", PREPARE));
    expect(await screen.findByText("Нет доступа")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/students/5/parent-message?kind=absences&days=30");
  });
});
