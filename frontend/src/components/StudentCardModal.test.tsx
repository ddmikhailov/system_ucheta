import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, downloadFile } from "../api/client";
import StudentCardModal from "./StudentCardModal";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, downloadFile: vi.fn() };
});

const download = vi.mocked(downloadFile);

function open(onClose = vi.fn()) {
  render(<StudentCardModal endpoint="/students/7/dossier/card" heading="Личная карточка обучающегося" filename="Личная_карточка_7.docx" onClose={onClose} />);
  return onClose;
}

const ALL = "full_name,group,gender,birth_date,birth_place,registration_address,enrollment_order,previous_education,absences,social_work";
const button = () => screen.getByRole("button", { name: "Скачать .docx" });

beforeEach(() => {
  download.mockReset();
  download.mockResolvedValue(undefined);
  localStorage.clear();
});

describe("StudentCardModal — личная карточка в Word", () => {
  it("по умолчанию отмечено всё, что есть в платформе, разделы учебной части сохраняются", async () => {
    const user = userEvent.setup();
    open();
    await user.click(button());
    expect(download).toHaveBeenCalledWith(`/students/7/dossier/card?fields=${ALL}&blank_sections=true`, "Личная_карточка_7.docx");
    expect(await screen.findByText(/Файл скачан/)).toBeInTheDocument();
  });

  it("набор «ФИО и группа» даёт почти пустой бланк; галочка учебной части снимается", async () => {
    const user = userEvent.setup();
    open();
    await user.click(screen.getByRole("button", { name: /ФИО и группа/ }));
    expect(screen.getByRole("button", { name: /ФИО и группа/ })).toHaveClass("active");
    await user.click(screen.getByLabelText(/Оставить разделы учебной части/));
    await user.click(button());
    expect(download.mock.calls[0][0]).toBe("/students/7/dossier/card?fields=full_name,group&blank_sections=false");
  });

  it("поля идут в порядке бланка, а не по очереди нажатий", async () => {
    const user = userEvent.setup();
    open();
    await user.click(screen.getByRole("button", { name: /ФИО и группа/ }));
    await user.click(screen.getByLabelText(/Дата рождения/));
    await user.click(screen.getByLabelText(/Пол/));
    await user.click(button());
    expect(download.mock.calls[0][0]).toContain("fields=full_name,group,gender,birth_date&");
  });

  it("без полей скачать нельзя", async () => {
    const user = userEvent.setup();
    open();
    for (const f of [/^ФИО$/, /^Группа$/, /^Пол/, /^Дата рождения/, /^Место рождения/, /^Адрес регистрации/, /^Приказ о зачислении/, /^Образование до поступления/, /^Число пропущенных/, /^Общественная работа/]) {
      await user.click(screen.getByLabelText(f));
    }
    expect(button()).toBeDisabled();
    expect(screen.getByText("Выберите хотя бы одно поле.")).toBeInTheDocument();
  });

  it("ошибка сервера показывается, окно остаётся открытым", async () => {
    const user = userEvent.setup();
    download.mockRejectedValue(new ApiError(404, "Студент не числится в группе"));
    const onClose = open();
    await user.click(button());
    expect(await screen.findByText("Студент не числится в группе")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("выбор запоминается; повреждённое сохранение не ломает окно; Esc закрывает", async () => {
    const user = userEvent.setup();
    const first = render(<StudentCardModal endpoint="/x" heading="h" filename="f.docx" onClose={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /ФИО и группа/ }));
    await user.click(screen.getByLabelText(/Оставить разделы учебной части/));
    await user.click(button());
    first.unmount();
    render(<StudentCardModal endpoint="/x" heading="h" filename="f.docx" onClose={vi.fn()} />);
    expect(screen.getByLabelText(/^Дата рождения/)).not.toBeChecked();
    expect(screen.getByLabelText(/Оставить разделы учебной части/)).not.toBeChecked();

    localStorage.setItem("kait20.studentCard", "{не json");
    const onClose = open();
    expect(screen.getAllByLabelText(/^ФИО$/).length).toBeGreaterThan(0);
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });
});
