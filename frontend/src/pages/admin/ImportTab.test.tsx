import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, downloadFile, uploadFile } from "../../api/client";
import { renderPage } from "../../test/utils";
import { dialogs } from "../../utils/feedback";
import ImportTab from "./ImportTab";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, downloadFile: vi.fn(), uploadFile: vi.fn() };
});

const upload = vi.mocked(uploadFile);
const download = vi.mocked(downloadFile);
const FILE = new File(["x"], "kontingent.xlsx");

const report = (over = {}) => ({
  counts: { "групп создано": 1, "студентов создано": 2 },
  total_changes: 3,
  changes: [
    { sheet: "Группы", action: "создана", label: "Группа ТЕСТ111", detail: "1 курс, Диджитал" },
    { sheet: "Студенты", action: "создан", label: "Тестов Иван", detail: "группа ТЕСТ111" },
    { sheet: "Студенты", action: "создан", label: "Образцова Анна", detail: "группа ТЕСТ111" },
  ],
  changes_truncated: false, errors: [], warnings: [], needs_confirmation: null, sheets: ["Группы", "Студенты"],
  ...over,
});

beforeEach(() => {
  upload.mockReset();
  download.mockReset();
  download.mockResolvedValue(undefined);
});

async function pickFile(user: ReturnType<typeof userEvent.setup>, file = FILE) {
  await user.upload(screen.getByLabelText("Файл Excel с контингентом"), file);
}

describe("ImportTab", () => {
  it("скачивает шаблон с данными и пустой", async () => {
    const user = userEvent.setup();
    renderPage(<ImportTab />, { role: "admin" });
    await user.click(screen.getByRole("button", { name: "Шаблон с текущими данными" }));
    await user.click(screen.getByRole("button", { name: "Пустой шаблон" }));
    expect(download).toHaveBeenNthCalledWith(1, "/contingent-import/template", "kait20_contingent.xlsx");
    expect(download).toHaveBeenNthCalledWith(2, "/contingent-import/template?with_data=false", "kait20_contingent_empty.xlsx");
  });

  it("«Проверить файл» недоступна без файла; предпросмотр показывает итоги и изменения, записи ещё нет", async () => {
    const user = userEvent.setup();
    upload.mockResolvedValue(report());
    renderPage(<ImportTab />, { role: "admin" });
    expect(screen.getByRole("button", { name: "Проверить файл" })).toBeDisabled();
    await pickFile(user);
    await user.click(screen.getByRole("button", { name: "Проверить файл" }));
    expect(upload).toHaveBeenCalledWith("/contingent-import/preview?absent_students=keep", FILE);
    const totals = await screen.findByLabelText("Итоги проверки");
    expect(within(totals).getByText("групп создано")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Тестов Иван" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Показано 3 из 3");
  });

  it("настройки уходят параметрами запроса; их смена сбрасывает устаревший предпросмотр", async () => {
    const user = userEvent.setup();
    upload.mockResolvedValue(report());
    renderPage(<ImportTab />, { role: "admin" });
    await pickFile(user);
    await user.selectOptions(screen.getByLabelText("Студенты, которых нет в файле"), "expel");
    await user.click(screen.getByLabelText("Заменять действующих кураторов"));
    await user.click(screen.getByLabelText("Выдать временные пароли новым кураторам"));
    await user.click(screen.getByLabelText("Создавать новые отделения"));
    await user.click(screen.getByRole("button", { name: "Проверить файл" }));
    expect(upload).toHaveBeenCalledWith(
      "/contingent-import/preview?absent_students=expel&replace_curators=true&create_departments=true&issue_passwords=true", FILE);
    await screen.findByLabelText("Итоги проверки");
    await user.click(screen.getByLabelText("Заменять действующих кураторов"));
    expect(screen.queryByLabelText("Итоги проверки")).not.toBeInTheDocument();
  });

  it("с ошибками запись заблокирована, ошибки перечислены по листам и строкам", async () => {
    const user = userEvent.setup();
    upload.mockResolvedValue(report({ counts: {}, changes: [], errors: [{ sheet: "Студенты", row: 7, message: "группа «НЕТ» не найдена" }] }));
    renderPage(<ImportTab />, { role: "admin" });
    await pickFile(user);
    await user.click(screen.getByRole("button", { name: "Проверить файл" }));
    expect(await screen.findByText(/запись невозможна/)).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "группа «НЕТ» не найдена" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Записать в базу" })).toBeDisabled();
  });

  it("массовое выбытие требует отдельного подтверждения", async () => {
    const user = userEvent.setup();
    upload.mockResolvedValue(report({ needs_confirmation: "Файл отметил бы «отчислен» 15 из 20 студентов" }));
    renderPage(<ImportTab />, { role: "admin" });
    await pickFile(user);
    await user.click(screen.getByRole("button", { name: "Проверить файл" }));
    await screen.findByText(/15 из 20/);
    expect(screen.getByRole("button", { name: "Записать в базу" })).toBeDisabled();
    await user.click(screen.getByLabelText("Подтверждаю массовое выбытие"));
    expect(screen.getByRole("button", { name: "Записать в базу" })).toBeEnabled();
  });

  it("запись: подтверждение → apply → итоги и пароли показываются один раз", async () => {
    const user = userEvent.setup();
    vi.spyOn(dialogs, "confirm").mockResolvedValue(true);
    upload.mockResolvedValueOnce(report());
    upload.mockResolvedValueOnce({ ...report(), credentials: [{ full_name: "Куратова Мария", department: "Диджитал", username: "kuratova.m", password: "Abc123xyz789" }] });
    renderPage(<ImportTab />, { role: "admin" });
    await pickFile(user);
    await user.click(screen.getByRole("button", { name: "Проверить файл" }));
    await user.click(await screen.findByRole("button", { name: "Записать в базу" }));
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(2));
    expect(upload).toHaveBeenLastCalledWith("/contingent-import/apply?absent_students=keep", FILE);
    expect(await screen.findByText(/Временные пароли показаны один раз/)).toBeInTheDocument();
    expect(screen.getByText("Abc123xyz789")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Скачать список паролей (CSV)" })).toBeInTheDocument();
  });

  it("отказ в подтверждении ничего не записывает; ошибка сервера показывается", async () => {
    const user = userEvent.setup();
    vi.spyOn(dialogs, "confirm").mockResolvedValue(false);
    upload.mockResolvedValue(report());
    renderPage(<ImportTab />, { role: "admin" });
    await pickFile(user);
    await user.click(screen.getByRole("button", { name: "Проверить файл" }));
    await user.click(await screen.findByRole("button", { name: "Записать в базу" }));
    expect(upload).toHaveBeenCalledTimes(1);

    upload.mockRejectedValueOnce(new ApiError(400, "Файл не принят: не xlsx-файл"));
    await user.click(screen.getByRole("button", { name: "Проверить файл" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("не xlsx-файл");
  });

  it("файл больше 5 МБ отклоняется сразу", async () => {
    const user = userEvent.setup();
    renderPage(<ImportTab />, { role: "admin" });
    await pickFile(user, new File([new Uint8Array(5 * 1024 * 1024 + 1)], "big.xlsx"));
    expect(screen.getByRole("alert")).toHaveTextContent("больше 5 МБ");
    expect(screen.getByRole("button", { name: "Проверить файл" })).toBeDisabled();
  });

  it("поиск и фильтр по листу в списке изменений", async () => {
    const user = userEvent.setup();
    upload.mockResolvedValue(report());
    renderPage(<ImportTab />, { role: "admin" });
    await pickFile(user);
    await user.click(screen.getByRole("button", { name: "Проверить файл" }));
    await screen.findByLabelText("Итоги проверки");
    await user.click(screen.getByRole("button", { name: "Группы" }));
    expect(screen.queryByRole("cell", { name: "Тестов Иван" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Все" }));
    await user.type(screen.getByLabelText("Поиск по изменениям"), "Образцова");
    expect(screen.queryByRole("cell", { name: "Тестов Иван" })).not.toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Образцова Анна" })).toBeInTheDocument();
  });
});
