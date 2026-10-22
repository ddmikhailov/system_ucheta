import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as reporting from "../utils/errorReporting";
import ErrorBoundary from "./ErrorBoundary";

function Broken({ message }: { message: string }): never {
  throw new Error(message);
}

beforeEach(() => {
  // React пишет пойманную ошибку в консоль — в выводе тестов это шум.
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});

describe("ErrorBoundary", () => {
  it("без сбоя показывает содержимое", () => {
    render(<ErrorBoundary><p>раздел</p></ErrorBoundary>);
    expect(screen.getByText("раздел")).toBeInTheDocument();
  });

  it("сбой раздела: сообщение вместо белого экрана, кнопка «Обновить страницу», ошибка уходит на сервер", () => {
    const report = vi.spyOn(reporting, "reportClientError").mockImplementation(() => undefined);
    render(<ErrorBoundary><Broken message="нет данных" /></ErrorBoundary>);
    expect(screen.getByRole("alert")).toHaveTextContent("Что-то пошло не так");
    expect(screen.getByRole("button", { name: "Обновить страницу" })).toBeInTheDocument();
    expect(report).toHaveBeenCalledWith(expect.objectContaining({ message: "нет данных" }));
  });

  it("устаревшие файлы после обновления — просит обновить страницу", () => {
    vi.spyOn(reporting, "reportClientError").mockImplementation(() => undefined);
    render(<ErrorBoundary><Broken message="Failed to fetch dynamically imported module: /assets/AdminPage-abc.js" /></ErrorBoundary>);
    expect(screen.getByRole("alert")).toHaveTextContent("Платформа обновилась");
  });
});
