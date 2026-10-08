import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import DayNavigator from "./DayNavigator";

function setup(wide: boolean) {
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: wide && q.includes("min-width"), media: q }));
  const { container } = render(<DayNavigator date="2026-10-07" today="2026-10-07" monthStatus={[]} onChange={() => undefined} />);
  return container.querySelector(".day-nav") as HTMLElement;
}

afterEach(() => vi.unstubAllGlobals());

describe("DayNavigator — кнопка календаря", () => {
  it("на телефоне календарь свёрнут, кнопка раскрывает и снова скрывает", async () => {
    const user = userEvent.setup();
    const nav = setup(false);
    expect(nav).not.toHaveClass("is-calendar-open");
    await user.click(screen.getByRole("button", { name: "Календарь" }));
    expect(nav).toHaveClass("is-calendar-open");
    await user.click(screen.getByRole("button", { name: "Скрыть календарь" }));
    expect(nav).not.toHaveClass("is-calendar-open");
  });

  it("на широком экране календарь открыт и тоже скрывается кнопкой", async () => {
    const user = userEvent.setup();
    const nav = setup(true);
    expect(nav).toHaveClass("is-calendar-open");
    await user.click(screen.getByRole("button", { name: "Скрыть календарь" }));
    expect(nav).not.toHaveClass("is-calendar-open");
  });
});
