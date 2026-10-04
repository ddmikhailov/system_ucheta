import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, downloadFile } from "../api/client";
import { renderPage } from "../test/utils";
import { toIso } from "../utils/date";
import AbsenceSheetButton from "./AbsenceSheetButton";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, downloadFile: vi.fn() };
});

const download = vi.mocked(downloadFile);

beforeEach(() => {
  download.mockReset();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 9, 14, 12, 0)); // 14.10.2026
});

afterEach(() => {
  vi.useRealTimers();
});

function open() {
  return renderPage(<AbsenceSheetButton studentId={5} lastName="Лебедева" groupCode="СА172" />, { role: "curator" });
}

describe("AbsenceSheetButton", () => {
  it("по умолчанию — с начала текущего месяца по сегодня; скачивает .docx с понятным именем", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    download.mockResolvedValue(undefined);
    open();
    expect(screen.getByLabelText("С")).toHaveValue("2026-10-01");
    expect(screen.getByLabelText("По")).toHaveValue("2026-10-14");
    await user.click(screen.getByRole("button", { name: "Сформировать .docx" }));
    expect(download).toHaveBeenCalledWith(
      "/students/5/absence-sheet?date_from=2026-10-01&date_to=2026-10-14", "Лист_ознакомления_Лебедева_СА172.docx",
    );
    expect(await screen.findByText(/Файл сформирован и скачан/)).toBeInTheDocument();
  });

  it("выбранный период и галочка «пропуски по уважительной причине» уходят в запрос", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    download.mockResolvedValue(undefined);
    open();
    fireEvent.change(screen.getByLabelText("С"), { target: { value: "2026-09-01" } });
    fireEvent.change(screen.getByLabelText("По"), { target: { value: "2026-09-30" } });
    await user.click(screen.getByLabelText(/Добавить пропуски по уважительной причине/));
    await user.click(screen.getByRole("button", { name: "Сформировать .docx" }));
    expect(download.mock.calls[0][0]).toBe("/students/5/absence-sheet?date_from=2026-09-01&date_to=2026-09-30&include_excused=true");
  });

  it("«По» не позже сегодняшнего дня, «С» не позже «По»", () => {
    open();
    expect(screen.getByLabelText("По")).toHaveAttribute("max", toIso(new Date()));
    expect(screen.getByLabelText("По")).toHaveAttribute("min", "2026-10-01");
    expect(screen.getByLabelText("С")).toHaveAttribute("max", "2026-10-14");
  });

  it("сообщение сервера показано, повторная попытка возможна", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    download.mockRejectedValueOnce(new ApiError(400, "За выбранный период у студента нет пропусков и опозданий"));
    open();
    const button = screen.getByRole("button", { name: "Сформировать .docx" });
    await user.click(button);
    expect(await screen.findByText("За выбранный период у студента нет пропусков и опозданий")).toBeInTheDocument();
    expect(screen.queryByText(/Файл сформирован/)).not.toBeInTheDocument();
    expect(button).toBeEnabled();
    download.mockResolvedValue(undefined);
    await user.click(button);
    expect(await screen.findByText(/Файл сформирован и скачан/)).toBeInTheDocument();
    expect(screen.queryByText(/нет пропусков и опозданий/)).not.toBeInTheDocument();
  });

  it("неожиданная ошибка — общее сообщение", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    download.mockRejectedValue(new Error("сеть"));
    open();
    await user.click(screen.getByRole("button", { name: "Сформировать .docx" }));
    expect(await screen.findByText("Не удалось сформировать лист")).toBeInTheDocument();
  });
});
