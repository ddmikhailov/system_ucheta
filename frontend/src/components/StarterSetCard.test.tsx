import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import { renderPage } from "../test/utils";
import { dialogs } from "../utils/feedback";
import StarterSetCard from "./StarterSetCard";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  get.mockResolvedValue([{ week: 1, title: "Адаптация 1 курса: Знакомство с группой", due_date: "2026-11-09" }]);
});

describe("StarterSetCard", () => {
  it("показывает состав набора со сроками", async () => {
    renderPage(<StarterSetCard />, { role: "admin" });
    expect(await screen.findByText(/Знакомство с группой — срок/)).toBeInTheDocument();
  });

  it("после подтверждения ставит набор", async () => {
    const user = userEvent.setup();
    vi.spyOn(dialogs, "confirm").mockResolvedValue(true);
    post.mockResolvedValue([]);
    const onLaunched = vi.fn();
    renderPage(<StarterSetCard onLaunched={onLaunched} />, { role: "admin" });
    await user.click(screen.getByRole("button", { name: "Поставить задачи" }));
    expect(post).toHaveBeenCalledWith("/tasks/starter-sets/first-year", { start_date: expect.any(String) });
    expect(onLaunched).toHaveBeenCalled();
  });

  it("без подтверждения ничего не ставит", async () => {
    const user = userEvent.setup();
    vi.spyOn(dialogs, "confirm").mockResolvedValue(false);
    renderPage(<StarterSetCard />, { role: "admin" });
    await user.click(screen.getByRole("button", { name: "Поставить задачи" }));
    expect(post).not.toHaveBeenCalled();
  });

  it("ошибка сервера показана", async () => {
    const user = userEvent.setup();
    vi.spyOn(dialogs, "confirm").mockResolvedValue(true);
    post.mockRejectedValue(new ApiError(409, "Набор уже запускали"));
    renderPage(<StarterSetCard />, { role: "admin" });
    await user.click(screen.getByRole("button", { name: "Поставить задачи" }));
    expect(await screen.findByText("Набор уже запускали")).toBeInTheDocument();
  });
});
