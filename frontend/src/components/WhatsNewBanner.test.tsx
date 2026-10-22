import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { renderPage } from "../test/utils";
import { whatsNewState } from "../utils/whatsNew";
import WhatsNewBanner from "./WhatsNewBanner";

vi.mock("../constants/release", () => ({
  APP_VERSION: "9.9.0",
  WHATS_NEW: { "9.9.0": ["Кнопка «Сообщить о проблеме»", "Номер версии в меню"] },
}));

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const post = vi.mocked(api.post);

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue(undefined);
  whatsNewState.closedInThisTab = false;
});

describe("WhatsNewBanner", () => {
  it("показывается, пока пользователь не закрыл плашку этой версии", () => {
    renderPage(<WhatsNewBanner />, { role: "curator", user: { seen_release: "3.5.1" } });
    expect(screen.getByRole("heading", { name: "Что нового в версии 9.9.0" })).toBeInTheDocument();
    expect(screen.getByText("Номер версии в меню")).toBeInTheDocument();
  });

  it("не показывается, если эта версия уже просмотрена (в том числе на другом устройстве)", () => {
    renderPage(<WhatsNewBanner />, { role: "curator", user: { seen_release: "9.9.0" } });
    expect(screen.queryByRole("heading", { name: /Что нового/ })).not.toBeInTheDocument();
  });

  it("«Понятно» закрывает плашку, запоминает версию на сервере и не возвращает её в другом разделе", async () => {
    const user = userEvent.setup();
    const { unmount } = renderPage(<WhatsNewBanner />, { role: "curator", user: { seen_release: null } });
    await user.click(screen.getByRole("button", { name: "Понятно" }));
    expect(screen.queryByRole("heading", { name: /Что нового/ })).not.toBeInTheDocument();
    expect(post).toHaveBeenCalledWith("/support/release-seen", { release: "9.9.0" });

    unmount();
    renderPage(<WhatsNewBanner />, { role: "curator", user: { seen_release: null } });
    expect(screen.queryByRole("heading", { name: /Что нового/ })).not.toBeInTheDocument();
  });

  it("без входа ничего не показывает", () => {
    renderPage(<WhatsNewBanner />, { role: null });
    expect(screen.queryByRole("heading", { name: /Что нового/ })).not.toBeInTheDocument();
  });
});
