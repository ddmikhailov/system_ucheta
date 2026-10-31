import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import PdChangesList from "./PdChangesList";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);

describe("PdChangesList", () => {
  beforeEach(() => vi.clearAllMocks());

  it("показывает поля без значений", async () => {
    get.mockResolvedValue([
      { created_at: "2026-10-20T09:00:00", student_id: 10, student_name: "Тест Студент", group_code: "ГД-1", changed_by_name: "Куратор", changes: ["фамилия", "телефон"] },
    ]);
    render(<MemoryRouter><PdChangesList /></MemoryRouter>);
    expect(await screen.findByText("фамилия, телефон")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(expect.stringMatching(/^\/admin\/pd-changes\?month=\d{4}-\d{2}-01$/));
  });

  it("пустой месяц — понятное сообщение", async () => {
    get.mockResolvedValue([]);
    render(<MemoryRouter><PdChangesList /></MemoryRouter>);
    expect(await screen.findByText("За этот месяц изменений нет.")).toBeInTheDocument();
  });
});
