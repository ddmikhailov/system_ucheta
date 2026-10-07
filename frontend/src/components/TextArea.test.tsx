import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef, useState } from "react";
import { describe, expect, it } from "vitest";
import TextArea from "./TextArea";

function Host() {
  const [value, setValue] = useState("Начало");
  return (
    <label>
      Итог беседы
      <TextArea expandTitle="Итог беседы" value={value} maxLength={100} onChange={(e) => setValue(e.target.value)} />
    </label>
  );
}

describe("TextArea", () => {
  it("растягивать мышью нельзя; «на весь экран» открывает то же поле, текст общий, Esc и «Готово» закрывают", async () => {
    const user = userEvent.setup();
    render(<Host />);
    const field = screen.getByLabelText("Итог беседы");
    expect(field).toHaveClass("textarea-auto");

    await user.click(screen.getByRole("button", { name: "Развернуть на весь экран" }));
    const dialog = screen.getByRole("dialog", { name: "Итог беседы" });
    const big = dialog.querySelector("textarea") as HTMLTextAreaElement;
    expect(big).toHaveValue("Начало");
    expect(big).toHaveFocus();
    await user.type(big, " и конец");
    expect(screen.getByText("14 / 100")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Готово" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(field).toHaveValue("Начало и конец");

    await user.click(screen.getByRole("button", { name: "Развернуть на весь экран" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("только чтение: текст не правится ни в поле, ни в окне на весь экран", async () => {
    const user = userEvent.setup();
    render(<TextArea expandTitle="Сообщение" readOnly value="Готовый текст" onChange={() => {}} aria-label="Текст" />);
    expect(screen.getByLabelText("Текст")).toHaveAttribute("readonly");
    await user.click(screen.getByRole("button", { name: "Развернуть на весь экран" }));
    const big = screen.getByRole("dialog", { name: "Сообщение" }).querySelector("textarea") as HTMLTextAreaElement;
    expect(big).toHaveAttribute("readonly");
    expect(big).toHaveValue("Готовый текст");
  });

  it("ссылка на поле снаружи работает (например, вернуть фокус при ошибке)", () => {
    const ref = createRef<HTMLTextAreaElement>();
    render(<TextArea inputRef={ref} value="" onChange={() => {}} aria-label="Комментарий" />);
    expect(ref.current).toBe(screen.getByLabelText("Комментарий"));
    ref.current?.focus();
    expect(screen.getByLabelText("Комментарий")).toHaveFocus();
  });
});
