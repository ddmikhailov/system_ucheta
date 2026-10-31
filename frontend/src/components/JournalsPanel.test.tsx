import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, uploadFile } from "../api/client";
import type { JournalGrid, JournalImportReport, JournalSubject } from "../api/types";
import { renderPage } from "../test/utils";
import JournalsPanel from "./JournalsPanel";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }, uploadFile: vi.fn() };
});

const get = vi.mocked(api.get);
const upload = vi.mocked(uploadFile);

const SUBJECT: JournalSubject = { code: "МДК.01.01", name: "Компьютерные сети", lessons: 3, first_on: "2026-09-01", last_on: "2026-09-08" };

const GRID: JournalGrid = {
  code: "МДК.01.01",
  name: "Компьютерные сети",
  lessons: [
    { key: "2026-09-01#1", date: "2026-09-01", slot: 1, topic: "Классификация сетей", homework: null },
    { key: "2026-09-01#2", date: "2026-09-01", slot: 2, topic: "Классификация сетей", homework: "стр. 5" },
    { key: "2026-09-08#1", date: "2026-09-08", slot: 1, topic: null, homework: null },
  ],
  students: [
    { student_id: 1, full_name: "Тестов Иван", cells: { "2026-09-01#1": "5", "2026-09-01#2": "н", "2026-09-08#1": "2" }, average: 3.5, absent_hours: 1, twos: 1, low_average: true },
    { student_id: 2, full_name: "Проверкина Анна", cells: {}, average: null, absent_hours: 0, twos: 0, low_average: false },
  ],
};

function mock(subjects: JournalSubject[]) {
  get.mockImplementation(async (path: string) => {
    if (path === "/journal/groups/7/subjects") return subjects;
    if (path === "/journal/groups/7/subjects/%D0%9C%D0%94%D0%9A.01.01") return GRID;
    if (path === "/journal/groups/7/discrepancies") return [];
    throw new Error(`неожиданный запрос ${path}`);
  });
}

describe("JournalsPanel", () => {
  beforeEach(() => {
    get.mockReset();
    upload.mockReset();
  });

  it("показывает пустое состояние, пока журналы не загружены", async () => {
    mock([]);
    renderPage(<JournalsPanel groupId={7} />, { role: "curator" });
    expect(await screen.findByText(/Журналы ещё не загружены/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Загрузить журнал из Excel…" })).toBeInTheDocument();
  });

  it("рисует журнал: оценки, «н» и темы уроков", async () => {
    mock([SUBJECT]);
    renderPage(<JournalsPanel groupId={7} />, { role: "curator" });
    const row = (await screen.findByRole("row", { name: /Тестов Иван/ })) as HTMLElement;
    const cells = within(row).getAllByRole("cell");
    // ср. балл, часы «н», затем по столбцу на час
    expect(cells.map((c) => c.textContent)).toEqual(["3,5", "1", "5", "н", "2"]);
    expect(within(screen.getByRole("row", { name: /Проверкина Анна/ })).getAllByRole("cell")[0].textContent).toBe("—");
    expect(screen.getByRole("columnheader", { name: "08.09" })).toBeInTheDocument();
    // средняя ниже 4 и «двойка» — куратору подсказка
    expect(screen.getByRole("status")).toHaveTextContent("Тестов Иван — средняя 3,5 — задолженность: оценок «2» — 1");
    expect(screen.getByRole("status")).not.toHaveTextContent("Проверкина");
    await userEvent.click(screen.getByText(/Темы уроков и домашние задания \(2\)/));
    expect(screen.getByText(/задание: стр. 5/)).toBeInTheDocument();
  });

  it("проверка файла не пишет в базу, загрузка пишет и обновляет список", async () => {
    mock([]);
    const report: JournalImportReport = {
      subject_code: "МДК.01.01", subject_name: "Компьютерные сети", period_from: "2026-09-01", period_to: "2026-09-22",
      counts: { students_matched: 30, grades_new: 83, absences_new: 163 }, warnings: ["Значение «ку» встретилось 1 раз(а)"],
      not_found: ["Нет Такого"], ambiguous: [], out_of_scope: [], blocked: null, applied: false,
    };
    upload.mockResolvedValueOnce(report).mockResolvedValueOnce({ ...report, applied: true });
    renderPage(<JournalsPanel groupId={7} />, { role: "curator" });
    await userEvent.click(await screen.findByRole("button", { name: "Загрузить журнал из Excel…" }));
    const file = new File(["x"], "journal.xlsx");
    await userEvent.upload(document.querySelector('input[type="file"]') as HTMLInputElement, file);
    await userEvent.click(screen.getByRole("button", { name: "Проверить файл" }));
    expect(upload).toHaveBeenLastCalledWith("/journal/preview", file);
    expect(await screen.findByText("83")).toBeInTheDocument();
    expect(screen.getByText(/Не найдены в платформе: 1/)).toBeInTheDocument();

    mock([SUBJECT]);
    await userEvent.click(screen.getByRole("button", { name: "Загрузить журнал" }));
    await waitFor(() => expect(upload).toHaveBeenLastCalledWith("/journal/apply", file));
    expect(await screen.findByText("Журнал загружен.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /МДК.01.01 Компьютерные сети/ })).toBeInTheDocument();
  });

  it("заблокированный отчёт не предлагает загрузку", async () => {
    mock([]);
    upload.mockResolvedValueOnce({
      subject_code: "X", subject_name: "Y", period_from: null, period_to: null, counts: {}, warnings: [], not_found: [], ambiguous: [],
      out_of_scope: [], blocked: "Ни один студент журнала не найден", applied: false,
    });
    renderPage(<JournalsPanel groupId={7} />, { role: "curator" });
    await userEvent.click(await screen.findByRole("button", { name: "Загрузить журнал из Excel…" }));
    await userEvent.upload(document.querySelector('input[type="file"]') as HTMLInputElement, new File(["x"], "j.xlsx"));
    await userEvent.click(screen.getByRole("button", { name: "Проверить файл" }));
    expect(await screen.findByText("Ни один студент журнала не найден")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Загрузить журнал" })).not.toBeInTheDocument();
  });
});
