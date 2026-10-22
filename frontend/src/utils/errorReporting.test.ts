import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { installErrorReporting, reportClientError, resetErrorReporting } from "./errorReporting";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const post = vi.mocked(api.post);

beforeEach(() => {
  resetErrorReporting();
  post.mockReset();
  post.mockResolvedValue(undefined);
  window.history.pushState({}, "", "/my-day?date=2026-10-21");
});

describe("reportClientError", () => {
  it("отправляет ошибку со стеком и контекстом страницы", () => {
    reportClientError(new TypeError("x is undefined"));
    expect(post).toHaveBeenCalledWith("/support/client-error", expect.objectContaining({
      message: "TypeError: x is undefined",
      stack: expect.stringContaining("TypeError"),
      page: "/my-day",
    }));
  });

  it("ошибки ответов сервера не шлёт: сервер видит их сам", () => {
    reportClientError(new ApiError(500, "Internal Server Error"));
    expect(post).not.toHaveBeenCalled();
  });

  it("одну и ту же ошибку шлёт один раз, и не больше пяти разных за загрузку страницы", () => {
    reportClientError(new Error("одна"));
    reportClientError(new Error("одна"));
    expect(post).toHaveBeenCalledTimes(1);
    for (let i = 0; i < 10; i++) reportClientError(new Error(`ошибка ${i}`));
    expect(post).toHaveBeenCalledTimes(5);
  });

  it("сбой отправки не порождает новую ошибку", async () => {
    post.mockRejectedValue(new Error("нет сети"));
    expect(() => reportClientError(new Error("сбой"))).not.toThrow();
    await Promise.resolve();
  });
});

describe("installErrorReporting", () => {
  let uninstall: () => void = () => undefined;
  afterEach(() => uninstall());

  it("ловит необработанные ошибки и отклонённые промисы страницы", () => {
    uninstall = installErrorReporting();
    window.dispatchEvent(new ErrorEvent("error", { error: new RangeError("за пределами") }));
    const rejection = new Event("unhandledrejection") as PromiseRejectionEvent;
    Object.defineProperty(rejection, "reason", { value: new Error("промис отклонён") });
    window.dispatchEvent(rejection);
    const messages = post.mock.calls.map(([, body]) => (body as { message: string }).message);
    expect(messages).toEqual(["RangeError: за пределами", "Error: промис отклонён"]);
  });

  it("после отписки больше не слушает", () => {
    installErrorReporting()();
    // Без единого слушателя jsdom считает событие необработанной ошибкой теста.
    const swallow = (e: Event) => e.preventDefault();
    window.addEventListener("error", swallow);
    window.dispatchEvent(new ErrorEvent("error", { error: new Error("после отписки"), cancelable: true }));
    window.removeEventListener("error", swallow);
    expect(post).not.toHaveBeenCalled();
  });
});
