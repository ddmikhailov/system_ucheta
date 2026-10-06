import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, downloadFile } from "../api/client";
import type { CuratorReport, ReportField } from "../api/types";
import { renderPage } from "../test/utils";
import ReportPage from "./ReportPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }, downloadFile: vi.fn() };
});

const get = vi.mocked(api.get);
const put = vi.mocked(api.put);
const download = vi.mocked(downloadFile);

function field(key: string, label: string, over: Partial<ReportField> = {}): ReportField {
  return { key, label, hint: null, long: false, auto: null, value: null, ...over };
}

function report(over: Partial<CuratorReport> = {}): CuratorReport {
  return {
    group_id: 7, group_code: "СА172", school_year: "2026-2027", semester: 1, period_from: "2026-09-01", period_to: "2027-01-31",
    years: ["2026-2027", "2025-2026"], updated_at: null, can_edit: true,
    sections: [
      { key: "general", title: "Общие данные", fields: [
        field("g_students", "Количество студентов", { auto: "25" }),
        field("g_iup", "Переведённых на ИУП"),
        field("g_unexcused", "Отсутствие по неуважительным причинам, средний % за период", { auto: "3,2 %", hint: "доля пропусков без уважительной причины" }),
      ] },
      { key: "selfgov", title: "Организация самоуправления в группе", fields: [field("s_1", "Актив группы", { long: true })] },
    ],
    ...over,
  };
}

function mock(r: CuratorReport) {
  get.mockImplementation(async (path: string) => {
    if (path === "/individual-work/groups") return [{ id: 7, code: "СА172", course: 1 }];
    if (path.startsWith("/reports/groups/7")) {
      const query = new URLSearchParams(path.split("?")[1] ?? "");
      return { ...r, school_year: query.get("year") ?? r.school_year, semester: Number(query.get("semester") ?? r.semester) };
    }
    throw new Error(`неожиданный запрос ${path}`);
  });
}

beforeEach(() => {
  for (const m of [get, put, download]) m.mockReset();
  download.mockResolvedValue(undefined);
});

describe("ReportPage — отчёт куратора", () => {
  it("показывает разделы и то, что насчитала платформа, рядом с полем", async () => {
    mock(report());
    renderPage(<ReportPage />, { role: "curator" });
    expect(await screen.findByRole("heading", { name: "Общие данные" })).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/reports/groups/7");
    const students = screen.getByLabelText("Количество студентов");
    expect(students).toHaveValue("");
    expect(students).toHaveAttribute("placeholder", "25");
    expect(screen.getByText("25", { selector: "b" })).toBeInTheDocument();
    expect(screen.getByText(/Период: 01\.09\.2026 — 31\.01\.2027/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeDisabled();  // менять пока нечего
  });

  it("«Взять» подставляет посчитанное; ручные цифры сохраняются одним запросом (пустые не уходят)", async () => {
    const user = userEvent.setup();
    mock(report());
    put.mockResolvedValue(report());
    renderPage(<ReportPage />, { role: "curator" });
    await screen.findByRole("heading", { name: "Общие данные" });
    await user.click(screen.getByRole("button", { name: "Взять посчитанное: Количество студентов" }));
    expect(screen.getByLabelText("Количество студентов")).toHaveValue("25");
    await user.type(screen.getByLabelText("Переведённых на ИУП"), "2");
    await user.type(screen.getByLabelText("Актив группы"), "Иванов И.");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(put).toHaveBeenCalledWith("/reports/groups/7?year=2026-2027&semester=1", {
      values: { g_students: "25", g_iup: "2", s_1: "Иванов И." },
    });
    expect(await screen.findByText("Сохранено")).toBeInTheDocument();
  });

  it("уже внесённые значения показываются в полях; «Взять» исчезает, когда значение равно посчитанному", async () => {
    mock(report({ sections: [{ key: "general", title: "Общие данные", fields: [field("g_students", "Количество студентов", { auto: "25", value: "25" })] }] }));
    renderPage(<ReportPage />, { role: "curator" });
    expect(await screen.findByLabelText("Количество студентов")).toHaveValue("25");
    expect(screen.queryByRole("button", { name: /Взять посчитанное/ })).not.toBeInTheDocument();
  });

  it("Word: несохранённые правки сначала сохраняются, потом скачивается файл", async () => {
    const user = userEvent.setup();
    mock(report());
    put.mockResolvedValue(report());
    renderPage(<ReportPage />, { role: "curator" });
    await user.type(await screen.findByLabelText("Переведённых на ИУП"), "3");
    await user.click(screen.getByRole("button", { name: "Отчёт в Word" }));
    await waitFor(() => expect(download).toHaveBeenCalledWith("/reports/groups/7/report.docx?year=2026-2027&semester=1", "Отчёт_куратора_СА172_1_семестр.docx"));
    expect(put).toHaveBeenCalledTimes(1);
    expect(put.mock.invocationCallOrder[0]).toBeLessThan(download.mock.invocationCallOrder[0]);
  });

  it("если сохранить не вышло, файл не скачивается, а ошибка видна", async () => {
    const user = userEvent.setup();
    mock(report());
    put.mockRejectedValue(new ApiError(400, "Неизвестные показатели: x"));
    renderPage(<ReportPage />, { role: "curator" });
    await user.type(await screen.findByLabelText("Переведённых на ИУП"), "3");
    await user.click(screen.getByRole("button", { name: "Отчёт в Word" }));
    expect(await screen.findByText("Неизвестные показатели: x")).toBeInTheDocument();
    expect(download).not.toHaveBeenCalled();
  });

  it("семестр и год переключаются", async () => {
    const user = userEvent.setup();
    mock(report());
    renderPage(<ReportPage />, { role: "curator" });
    await user.selectOptions(await screen.findByLabelText("Семестр"), "2");
    await waitFor(() => expect(get).toHaveBeenCalledWith("/reports/groups/7?year=2026-2027&semester=2"));
    await user.selectOptions(screen.getByLabelText("Учебный год"), "2025-2026");
    await waitFor(() => expect(get).toHaveBeenCalledWith("/reports/groups/7?year=2025-2026&semester=2"));
  });

  it("только чтение: поля заблокированы, сохранить нельзя, выгрузка есть", async () => {
    const user = userEvent.setup();
    mock(report({ can_edit: false }));
    renderPage(<ReportPage />, { role: "social_pedagogue" });
    expect(await screen.findByLabelText("Количество студентов")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Сохранить" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Взять посчитанное/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Отчёт в Word" }));
    expect(put).not.toHaveBeenCalled();
    expect(download).toHaveBeenCalled();
    expect(within(screen.getByRole("heading", { name: "Общие данные" }).closest("section") as HTMLElement).getByText(/доля пропусков/)).toBeInTheDocument();
  });

  it("ошибка загрузки показывается", async () => {
    get.mockImplementation(async (path: string) => {
      if (path === "/individual-work/groups") return [{ id: 7, code: "СА172", course: 1 }];
      throw new ApiError(403, "Это не ваша группа");
    });
    renderPage(<ReportPage />, { role: "curator" });
    expect(await screen.findByText("Это не ваша группа")).toBeInTheDocument();
  });
});
