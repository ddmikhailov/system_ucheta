import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import FeedbackHost from "./FeedbackHost";
import { dialogs, resetFeedback, toast } from "../utils/feedback";

afterEach(() => {
  resetFeedback();
  vi.useRealTimers();
});

describe("FeedbackHost", () => {
  it("подтверждение показывается в приложении и возвращает ответ", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm");
    render(<FeedbackHost />);
    let answer: Promise<boolean> = Promise.resolve(false);
    act(() => {
      answer = dialogs.confirm("Удалить задачу «Кружки»?", { confirmLabel: "Удалить", danger: true });
    });
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("Удалить задачу «Кружки»?");
    await user.click(screen.getByRole("button", { name: "Удалить" }));
    await expect(answer).resolves.toBe(true);
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(confirm).not.toHaveBeenCalled();
  });

  it("«Отмена» и Esc отвечают «нет»", async () => {
    const user = userEvent.setup();
    render(<FeedbackHost />);
    let first: Promise<boolean> = Promise.resolve(true);
    act(() => {
      first = dialogs.confirm("Сменить группу?");
    });
    await user.click(await screen.findByRole("button", { name: "Отмена" }));
    await expect(first).resolves.toBe(false);

    let second: Promise<boolean> = Promise.resolve(true);
    act(() => {
      second = dialogs.confirm("Сменить дату?");
    });
    await screen.findByRole("alertdialog");
    await user.keyboard("{Escape}");
    await expect(second).resolves.toBe(false);
  });

  it("ввод текста: значение по умолчанию, пустое нельзя сохранить, отмена даёт null", async () => {
    const user = userEvent.setup();
    render(<FeedbackHost />);
    let name: Promise<string | null> = Promise.resolve(null);
    act(() => {
      name = dialogs.prompt("Название шаблона", "Кружки");
    });
    const input = await screen.findByRole("textbox", { name: "Название шаблона" });
    expect(input).toHaveValue("Кружки");
    await user.clear(input);
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeDisabled();
    await user.type(input, "Ежегодная сверка");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await expect(name).resolves.toBe("Ежегодная сверка");

    let cancelled: Promise<string | null> = Promise.resolve("x");
    act(() => {
      cancelled = dialogs.prompt("Название шаблона", "Кружки");
    });
    await user.click(await screen.findByRole("button", { name: "Отмена" }));
    await expect(cancelled).resolves.toBeNull();
  });

  it("второй диалог ждёт, пока закроют первый", async () => {
    const user = userEvent.setup();
    render(<FeedbackHost />);
    act(() => {
      void dialogs.confirm("Первый?");
      void dialogs.confirm("Второй?");
    });
    expect(await screen.findByRole("alertdialog")).toHaveTextContent("Первый?");
    await user.click(screen.getByRole("button", { name: "Да" }));
    expect(await screen.findByRole("alertdialog")).toHaveTextContent("Второй?");
  });

  it("без хоста падает обратно на системное окно, а не зависает", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    await expect(dialogs.confirm("Удалить?")).resolves.toBe(true);
    expect(confirm).toHaveBeenCalledWith("Удалить?");
  });

  it("сообщение показывается внизу и само исчезает", () => {
    vi.useFakeTimers();
    render(<FeedbackHost />);
    act(() => toast("Черновик сохранён"));
    expect(screen.getByRole("status")).toHaveTextContent("Черновик сохранён");
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.queryByText("Черновик сохранён")).not.toBeInTheDocument();
  });

  it("ошибка — с ролью alert, её можно закрыть", async () => {
    render(<FeedbackHost />);
    act(() => toast("Не удалось сохранить", "error"));
    expect(screen.getByRole("alert")).toHaveTextContent("Не удалось сохранить");
    await userEvent.setup().click(screen.getByRole("button", { name: "Скрыть сообщение" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
