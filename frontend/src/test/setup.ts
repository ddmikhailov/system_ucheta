import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

// jsdom не реализует прокрутку; страницы вызывают её при появлении ошибок/уведомлений.
beforeEach(() => {
  window.scrollTo = vi.fn();
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
