import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { APP_VERSION } from "../constants/release";
import * as feedback from "../utils/feedback";
import ProblemReportModal from "./ProblemReportModal";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const post = vi.mocked(api.post);

beforeEach(() => {
  post.mockReset();
  window.history.pushState({}, "", "/cabinet?group=5");
});

function open() {
  const onClose = vi.fn();
  render(<ProblemReportModal onClose={onClose} />);
  return onClose;
}

describe("ProblemReportModal", () => {
  it("показывает, что добавится к сообщению, и отправляет текст вместе со страницей, версией, браузером и экраном", async () => {
    const user = userEvent.setup();
    const toast = vi.spyOn(feedback, "toast");
    post.mockResolvedValue({ delivered: 2 });
    const onClose = open();

    expect(screen.getByRole("dialog", { name: "Сообщить о проблеме" })).toBeInTheDocument();
    // Только путь: в параметрах адреса бывают номера и поиск по ФИО.
    expect(screen.getByText("/cabinet")).toBeInTheDocument();
    expect(screen.getByText(APP_VERSION)).toBeInTheDocument();
    const send = screen.getByRole("button", { name: "Отправить" });
    expect(send).toBeDisabled();

    await user.type(screen.getByLabelText("Что случилось?"), "  Не сохраняются отметки  ");
    await user.click(send);

    expect(post).toHaveBeenCalledWith("/support/problem-report", expect.objectContaining({
      text: "Не сохраняются отметки",
      page: "/cabinet",
      version: APP_VERSION,
      browser: expect.any(String),
      screen: expect.stringMatching(/^\d+×\d+$/),
    }));
    expect(toast).toHaveBeenCalledWith("Сообщение отправлено администратору");
    expect(onClose).toHaveBeenCalled();
  });

  it("нет ни одного администратора — окно остаётся открытым с объяснением", async () => {
    const user = userEvent.setup();
    post.mockResolvedValue({ delivered: 0 });
    const onClose = open();
    await user.type(screen.getByLabelText("Что случилось?"), "Ошибка");
    await user.click(screen.getByRole("button", { name: "Отправить" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("нет активного администратора");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("ошибку сервера (например, лимит сообщений) показывает словами сервера", async () => {
    const user = userEvent.setup();
    post.mockRejectedValue(new ApiError(429, "Слишком много сообщений подряд — попробуйте через час"));
    open();
    await user.type(screen.getByLabelText("Что случилось?"), "Ошибка");
    await user.click(screen.getByRole("button", { name: "Отправить" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Слишком много сообщений подряд");
  });

  it("«Отмена» закрывает окно без отправки", async () => {
    const user = userEvent.setup();
    const onClose = open();
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(onClose).toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();
  });
});
