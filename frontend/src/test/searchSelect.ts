import { screen } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";

/** Выбрать вариант в списке с поиском (SearchSelect): открыть поле и кликнуть по пункту. */
export async function chooseOption(user: UserEvent, combobox: HTMLElement, name: string | RegExp) {
  await user.click(combobox);
  await user.click(screen.getByRole("option", { name }));
}
