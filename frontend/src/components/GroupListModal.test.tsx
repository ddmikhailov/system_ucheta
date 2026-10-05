import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, downloadFile } from "../api/client";
import GroupListModal from "./GroupListModal";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, downloadFile: vi.fn() };
});

const download = vi.mocked(downloadFile);

function open(onClose = vi.fn()) {
  render(<GroupListModal groupId={7} groupCode="СА172" onClose={onClose} />);
  return onClose;
}

const download_button = () => screen.getByRole("button", { name: "Скачать .docx" });

beforeEach(() => {
  download.mockReset();
  download.mockResolvedValue(undefined);
  localStorage.clear();
});

describe("GroupListModal — список группы для печати", () => {
  it("по умолчанию ФИО, телефон и e-mail: скачивается таблица из этих столбцов с нумерацией", async () => {
    const user = userEvent.setup();
    open();
    expect(screen.getByText(/В таблице столбцов: 4/)).toBeInTheDocument(); // «№» + три выбранных
    await user.click(download_button());
    expect(download).toHaveBeenCalledWith("/curator/groups/7/roster-sheet?fields=full_name,phone,email&numbering=true", "Список_СА172.docx");
    expect(await screen.findByText(/Файл скачан/)).toBeInTheDocument();
  });

  it("столбцы идут в порядке списка, а не по очереди нажатий; нумерацию можно убрать", async () => {
    const user = userEvent.setup();
    open();
    await user.click(screen.getByRole("button", { name: "Только ФИО" }));
    await user.click(screen.getByLabelText(/^Телефон$/));
    await user.click(screen.getByLabelText(/Дата рождения/)); // выбрана последней, но стоит раньше телефона
    await user.click(screen.getByLabelText(/Нумерация строк/));
    expect(screen.getByText(/В таблице столбцов: 3/)).toBeInTheDocument();
    await user.click(download_button());
    expect(download.mock.calls[0][0]).toBe("/curator/groups/7/roster-sheet?fields=full_name,birth_date,phone&numbering=false");
  });

  it("готовые наборы подставляют столбцы, выбранный набор подсвечен", async () => {
    const user = userEvent.setup();
    open();
    expect(screen.getByRole("button", { name: "ФИО, телефон, e-mail" })).toHaveClass("active");
    await user.click(screen.getByRole("button", { name: "С представителями" }));
    expect(screen.getByRole("button", { name: "С представителями" })).toHaveClass("active");
    expect(screen.getByLabelText(/Представители/)).toBeChecked();
    expect(screen.getByLabelText(/Телефоны представителей/)).toBeChecked();
    expect(screen.getByLabelText(/^Телефон$/)).not.toBeChecked();
  });

  it("заголовок кодируется для адреса; пустые столбцы «Подпись» и «Примечание» — обычные галочки", async () => {
    const user = userEvent.setup();
    open();
    await user.click(screen.getByRole("button", { name: "Для подписи" }));
    await user.type(screen.getByLabelText(/Заголовок/), "Экскурсия 12.10 & ещё");
    await user.click(download_button());
    expect(download.mock.calls[0][0]).toBe(`/curator/groups/7/roster-sheet?fields=full_name,signature&numbering=true&title=${encodeURIComponent("Экскурсия 12.10 & ещё")}`);
  });

  it("без столбцов скачать нельзя", async () => {
    const user = userEvent.setup();
    open();
    for (const name of [/^ФИО$/, /^Телефон$/, /^E-mail$/]) await user.click(screen.getByLabelText(name));
    expect(download_button()).toBeDisabled();
    expect(screen.getByText("Выберите хотя бы один столбец.")).toBeInTheDocument();
  });

  it("ошибка сервера показывается, окно остаётся открытым", async () => {
    const user = userEvent.setup();
    download.mockRejectedValue(new ApiError(400, "В группе нет студентов"));
    const onClose = open();
    await user.click(download_button());
    expect(await screen.findByText("В группе нет студентов")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.queryByText(/Файл скачан/)).not.toBeInTheDocument();
  });

  it("последний выбор запоминается и подставляется при следующем открытии", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<GroupListModal groupId={7} groupCode="СА172" onClose={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "С представителями" }));
    await user.click(screen.getByLabelText(/Нумерация строк/));
    await user.click(download_button());
    await waitFor(() => expect(localStorage.getItem("kait20.groupList")).not.toBeNull());
    unmount();

    render(<GroupListModal groupId={8} groupCode="ИИ212" onClose={vi.fn()} />);
    expect(screen.getByLabelText(/Представители/)).toBeChecked();
    expect(screen.getByLabelText(/Нумерация строк/)).not.toBeChecked();
  });

  it("повреждённое сохранённое значение не ломает окно", () => {
    localStorage.setItem("kait20.groupList", "{не json");
    open();
    expect(screen.getByLabelText(/^ФИО$/)).toBeChecked();
    localStorage.setItem("kait20.groupList", JSON.stringify({ keys: ["нет-такого"], numbering: false }));
  });

  it("Esc и кнопка «Закрыть» закрывают окно", async () => {
    const user = userEvent.setup();
    const onClose = open();
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Закрыть" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
