import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, downloadFile, uploadFile } from "../api/client";
import DossierImport from "./DossierImport";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, downloadFile: vi.fn(), uploadFile: vi.fn() };
});

const upload = vi.mocked(uploadFile);
const download = vi.mocked(downloadFile);

const FILE = new File(["x"], "dossier.xlsx", {
  type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
});

const preview = (over = {}) => ({
  total: 3, ready: 2, unchanged: 0, with_errors: 1,
  rows: [{ row: 3, label: "СА172 Иванов Иван", errors: ["студент не найден в этой группе"], will_update: false }],
  ...over,
});

async function openAndPick(user: ReturnType<typeof userEvent.setup>) {
  render(<DossierImport />);
  await user.click(screen.getByRole("button", { name: /Загрузить досье из Excel/ }));
  // Поле выбора файла не имеет подписи — берём по типу.
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  await user.upload(input, FILE);
}

beforeEach(() => {
  upload.mockReset();
  download.mockReset();
});

describe("DossierImport", () => {
  it("по умолчанию свёрнут", () => {
    render(<DossierImport />);
    expect(screen.getByRole("button", { name: /Загрузить досье из Excel/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Скачать шаблон" })).not.toBeInTheDocument();
  });

  it("скачивает шаблон", async () => {
    const user = userEvent.setup();
    download.mockResolvedValue(undefined);
    render(<DossierImport />);
    await user.click(screen.getByRole("button", { name: /Загрузить досье из Excel/ }));
    await user.click(screen.getByRole("button", { name: "Скачать шаблон" }));
    expect(download).toHaveBeenCalledWith("/dossier-import/template", "dossier_template.xlsx");
  });

  it("«Проверить файл» недоступна, пока файл не выбран", async () => {
    const user = userEvent.setup();
    render(<DossierImport />);
    await user.click(screen.getByRole("button", { name: /Загрузить досье из Excel/ }));
    expect(screen.getByRole("button", { name: "Проверить файл" })).toBeDisabled();
  });

  it("предпросмотр показывает счётчики и ошибки по строкам", async () => {
    const user = userEvent.setup();
    upload.mockResolvedValue(preview());
    await openAndPick(user);
    await user.click(screen.getByRole("button", { name: "Проверить файл" }));
    expect(upload).toHaveBeenCalledWith("/dossier-import/preview", FILE);
    expect(await screen.findByText("студент не найден в этой группе")).toBeInTheDocument();
    expect(screen.getByText("СА172 Иванов Иван")).toBeInTheDocument();
    expect(screen.getByText(/Строк:/).textContent).toMatch(/Строк:\s*3.*готово к записи:\s*2.*с ошибками:\s*1/);
  });

  it("запись с ошибками требует подтверждения; отказ ничего не отправляет", async () => {
    const user = userEvent.setup();
    upload.mockResolvedValueOnce(preview());
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await openAndPick(user);
    await user.click(screen.getByRole("button", { name: "Проверить файл" }));
    await user.click(await screen.findByRole("button", { name: /Записать 2/ }));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("Строк с ошибками: 1"));
    expect(upload).toHaveBeenCalledTimes(1); // только предпросмотр
  });

  it("подтверждённая запись применяет файл и сообщает итог", async () => {
    const user = userEvent.setup();
    upload.mockResolvedValueOnce(preview());
    upload.mockResolvedValueOnce({ updated: 2, skipped_with_errors: 1 });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await openAndPick(user);
    await user.click(screen.getByRole("button", { name: "Проверить файл" }));
    await user.click(await screen.findByRole("button", { name: /Записать 2/ }));
    expect(upload).toHaveBeenLastCalledWith("/dossier-import/apply", FILE);
    expect(await screen.findByText(/Обновлено студентов: 2, пропущено строк с ошибками: 1/)).toBeInTheDocument();
    // После записи повторно «Записать» не предлагаем.
    expect(screen.queryByRole("button", { name: /Записать/ })).not.toBeInTheDocument();
  });

  it("без ошибок записывает сразу, без вопроса", async () => {
    const user = userEvent.setup();
    upload.mockResolvedValueOnce(preview({ with_errors: 0, rows: [] }));
    upload.mockResolvedValueOnce({ updated: 2, skipped_with_errors: 0 });
    const confirm = vi.spyOn(window, "confirm");
    await openAndPick(user);
    await user.click(screen.getByRole("button", { name: "Проверить файл" }));
    await user.click(await screen.findByRole("button", { name: /Записать 2/ }));
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(2));
    expect(confirm).not.toHaveBeenCalled();
  });

  it("если записывать нечего, кнопки записи нет", async () => {
    const user = userEvent.setup();
    upload.mockResolvedValue(preview({ ready: 0, unchanged: 3, with_errors: 0, rows: [] }));
    await openAndPick(user);
    await user.click(screen.getByRole("button", { name: "Проверить файл" }));
    await screen.findByText(/Строк:/);
    expect(screen.queryByRole("button", { name: /Записать/ })).not.toBeInTheDocument();
  });

  it("ошибка сервера (например, не тот файл) показывается и не ломает форму", async () => {
    const user = userEvent.setup();
    upload.mockRejectedValue(new ApiError(400, "Заголовки не совпадают с шаблоном — скачайте шаблон заново"));
    await openAndPick(user);
    await user.click(screen.getByRole("button", { name: "Проверить файл" }));
    expect(await screen.findByText(/Заголовки не совпадают с шаблоном/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Проверить файл" })).toBeEnabled();
  });

  it("выбор другого файла сбрасывает прежний предпросмотр", async () => {
    const user = userEvent.setup();
    upload.mockResolvedValue(preview());
    await openAndPick(user);
    await user.click(screen.getByRole("button", { name: "Проверить файл" }));
    await screen.findByText(/Строк:/);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["y"], "other.xlsx"));
    expect(screen.queryByText(/Строк:/)).not.toBeInTheDocument();
  });

  it("можно закрыть блок", async () => {
    const user = userEvent.setup();
    render(<DossierImport />);
    await user.click(screen.getByRole("button", { name: /Загрузить досье из Excel/ }));
    await user.click(screen.getByRole("button", { name: "Закрыть" }));
    expect(screen.queryByRole("button", { name: "Скачать шаблон" })).not.toBeInTheDocument();
  });

  it("файл больше 5 МБ отклоняется сразу, без запроса на сервер", async () => {
    const user = userEvent.setup();
    render(<DossierImport />);
    await user.click(screen.getByRole("button", { name: /Загрузить досье из Excel/ }));
    const big = new File([new Uint8Array(5 * 1024 * 1024 + 1)], "big.xlsx");
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, big);
    expect(screen.getByText(/Файл больше 5 МБ/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Проверить|Предпросмотр/ })).toBeDisabled();
    expect(upload).not.toHaveBeenCalled();
  });
});
