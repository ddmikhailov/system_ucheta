import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import SearchSelect from "./SearchSelect";

const OPTIONS = [
  { value: "1", label: "ГД116" },
  { value: "2", label: "ГД136" },
  { value: "3", label: "ТИФ116" },
  { value: "4", label: "СА172" },
];

let current = "";  // последнее выбранное значение

function Harness({ allLabel, initial = "" }: { allLabel?: string; initial?: string }) {
  const [value, setValue] = useState(initial);
  return <SearchSelect value={value} options={OPTIONS} onChange={(v) => {
    current = v;
    setValue(v);
  }} allLabel={allLabel} ariaLabel="Группа" />;
}

const optionTexts = () => within(screen.getByRole("listbox")).getAllByRole("option").map((o) => o.textContent);

describe("SearchSelect", () => {
  it("открывается по клику, показывает все варианты и пункт «все» первым", async () => {
    const user = userEvent.setup();
    render(<Harness allLabel="Все группы" />);
    await user.click(screen.getByRole("combobox", { name: "Группа" }));
    expect(optionTexts()).toEqual(["Все группы", "ГД116", "ГД136", "ТИФ116", "СА172"]);
  });

  it("ввод «GD» оставляет группы с ГД, Enter выбирает первую", async () => {
    const user = userEvent.setup();
    render(<Harness allLabel="Все группы" />);
    const box = screen.getByRole("combobox", { name: "Группа" });
    await user.click(box);
    await user.type(box, "GD");
    expect(optionTexts()).toEqual(["ГД116", "ГД136"]);
    await user.keyboard("{Enter}");
    expect(current).toBe("1");
    expect(box).toHaveValue("ГД116");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("стрелки двигают выбор; клик по варианту выбирает его", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const box = screen.getByRole("combobox", { name: "Группа" });
    await user.click(box);
    await user.keyboard("{ArrowDown}{ArrowDown}{Enter}");
    expect(current).toBe("3");

    await user.click(box);
    await user.click(screen.getByRole("option", { name: "СА172" }));
    expect(current).toBe("4");
  });

  it("Esc закрывает список без выбора; ничего не найдено — сообщение", async () => {
    const user = userEvent.setup();
    render(<Harness initial="2" />);
    const box = screen.getByRole("combobox", { name: "Группа" });
    expect(box).toHaveValue("ГД136");
    await user.click(box);
    await user.type(box, "ЯЯЯ");
    expect(screen.getByText("Ничего не найдено")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(box).toHaveValue("ГД136"); // значение не изменилось
  });

  it("«Все группы» возвращает пустое значение", async () => {
    const user = userEvent.setup();
    render(<Harness allLabel="Все группы" initial="2" />);
    await user.click(screen.getByRole("combobox", { name: "Группа" }));
    await user.click(screen.getByRole("option", { name: "Все группы" }));
    expect(current).toBe("");
  });
});
