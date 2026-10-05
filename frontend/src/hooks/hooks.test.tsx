import { fireEvent, render, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useEscapeKey } from "./useEscapeKey";
import { useScrollToTopOnChange } from "./useScrollToTopOnChange";
import { useUnsavedWarning } from "./useUnsavedWarning";

describe("useEscapeKey", () => {
  it("вызывает закрытие по Esc и только по нему", () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Enter" });
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("после размонтирования обработчик снят", () => {
    const onClose = vi.fn();
    const { unmount } = render(<Harness onClose={onClose} />);
    unmount();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });
});

function Harness({ onClose }: { onClose: () => void }) {
  useEscapeKey(onClose);
  return null;
}

describe("useScrollToTopOnChange", () => {
  it("на первом показе не прокручивает", () => {
    renderHook(() => useScrollToTopOnChange(null, "ошибка уже была"));
    expect(window.scrollTo).not.toHaveBeenCalled();
  });

  it("прокручивает вверх, когда появилась ошибка или уведомление", () => {
    const { rerender } = renderHook(({ error, notice }) => useScrollToTopOnChange(error, notice), {
      initialProps: { error: null as string | null, notice: null as string | null },
    });
    rerender({ error: "Что-то пошло не так", notice: null });
    expect(window.scrollTo).toHaveBeenCalledTimes(1);
    rerender({ error: "Что-то пошло не так", notice: "Сохранено" });
    expect(window.scrollTo).toHaveBeenCalledTimes(2);
  });

  it("когда баннер пропал — не прокручивает", () => {
    const { rerender } = renderHook(({ error }) => useScrollToTopOnChange(error), {
      initialProps: { error: "ошибка" as string | null },
    });
    rerender({ error: null });
    expect(window.scrollTo).not.toHaveBeenCalled();
  });
});

describe("useUnsavedWarning", () => {
  function fireBeforeUnload() {
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    return event.defaultPrevented;
  }

  it("переспрашивает при уходе только пока есть несохранённое", () => {
    const { rerender, unmount } = renderHook(({ dirty }) => useUnsavedWarning(dirty), { initialProps: { dirty: false } });
    expect(fireBeforeUnload()).toBe(false);
    rerender({ dirty: true });
    expect(fireBeforeUnload()).toBe(true);
    rerender({ dirty: false });
    expect(fireBeforeUnload()).toBe(false);
    rerender({ dirty: true });
    unmount();
    expect(fireBeforeUnload()).toBe(false);
  });
});
