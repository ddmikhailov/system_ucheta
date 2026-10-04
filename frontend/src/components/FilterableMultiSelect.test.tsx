import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import FilterableMultiSelect from "./FilterableMultiSelect";

const OPTIONS = [
  { value: "1", label: "ГД116" },
  { value: "2", label: "ГД136" },
  { value: "3", label: "ТИФ116" },
  { value: "4", label: "СА172" },
];

let current: string[] = [];

function Harness({ initial = [] }: { initial?: string[] }) {
  const [selected, setSelected] = useState(initial);
  return <FilterableMultiSelect options={OPTIONS} selected={selected} onChange={(next) => {
    current = next;
    setSelected(next);
  }} ariaLabel="Группы" />;
}

const list = () => screen.getByRole("listbox", { name: "Группы" });
const labels = () => within(list()).getAllByRole("option").map((o) => o.textContent);

describe("FilterableMultiSelect", () => {
  it("поиск «GD» оставляет группы с ГД; без запроса — весь список", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(labels()).toEqual(["ГД116", "ГД136", "ТИФ116", "СА172"]);
    await user.type(screen.getByRole("searchbox", { name: "Поиск: Группы" }), "GD");
    expect(labels()).toEqual(["ГД116", "ГД136"]);
  });

  it("выбранные группы, скрытые поиском, не теряются; счётчик и «Снять выбор»", async () => {
    const user = userEvent.setup();
    render(<Harness initial={["4"]} />);
    expect(screen.getByText("Выбрано: 1")).toBeInTheDocument();

    await user.type(screen.getByRole("searchbox", { name: "Поиск: Группы" }), "ГД");
    await user.selectOptions(list(), "2");
    expect(current.sort()).toEqual(["2", "4"]);
    expect(screen.getByText("Выбрано: 2")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Снять выбор" }));
    expect(current).toEqual([]);
  });

  it("ничего не найдено — подсказка", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(screen.getByRole("searchbox"), "ЯЯЯ");
    expect(screen.getByText("Ничего не найдено")).toBeInTheDocument();
  });
});
