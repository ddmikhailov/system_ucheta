import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../api/client";
import { useApi } from "./useApi";

/** Подменённый api.get: каждый вызов ждёт, пока тест сам не ответит (resolve/reject). */
function deferredGet() {
  const calls: { path: string; signal?: AbortSignal; resolve: (v: unknown) => void; reject: (e: unknown) => void }[] = [];
  vi.spyOn(api, "get").mockImplementation((path: string, signal?: AbortSignal) => {
    return new Promise((resolve, reject) => {
      calls.push({ path, signal, resolve, reject });
      signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    });
  });
  return calls;
}

describe("useApi", () => {
  it("загружает данные и снимает признак загрузки", async () => {
    const calls = deferredGet();
    const { result } = renderHook(() => useApi<{ n: number }>("/a"));
    expect(result.current.loading).toBe(true);
    await act(async () => calls[0].resolve({ n: 1 }));
    expect(result.current.data).toEqual({ n: 1 });
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("смена адреса отменяет прежний запрос, его поздний ответ не затирает новый", async () => {
    const calls = deferredGet();
    const { result, rerender } = renderHook(({ path }) => useApi<string>(path), { initialProps: { path: "/groups/1" } });
    rerender({ path: "/groups/2" });
    expect(calls[0].signal?.aborted).toBe(true);
    await act(async () => calls[1].resolve("вторая"));
    await act(async () => calls[0].resolve("первая"));
    expect(result.current.data).toBe("вторая");
    expect(result.current.error).toBeNull();
  });

  it("со сменой адреса данные прежнего сбрасываются сразу", async () => {
    const calls = deferredGet();
    const { result, rerender } = renderHook(({ path }) => useApi<string>(path), { initialProps: { path: "/groups/1" } });
    await act(async () => calls[0].resolve("первая"));
    rerender({ path: "/groups/2" });
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(true);
  });

  it("ошибка сервера доходит до error с текстом сервера, иначе — с запасным текстом", async () => {
    const calls = deferredGet();
    const { result, rerender } = renderHook(({ path }) => useApi<string>(path, "Не удалось загрузить группу"), {
      initialProps: { path: "/a" },
    });
    await act(async () => calls[0].reject(new ApiError(403, "Это не ваша группа")));
    expect(result.current.error).toBe("Это не ваша группа");
    expect(result.current.loading).toBe(false);
    rerender({ path: "/b" });
    await act(async () => calls[1].reject(new TypeError("Failed to fetch")));
    expect(result.current.error).toBe("Не удалось загрузить группу");
  });

  it("path = null — запроса нет", () => {
    const calls = deferredGet();
    const { result } = renderHook(() => useApi<string>(null));
    expect(calls).toHaveLength(0);
    expect(result.current.loading).toBe(false);
  });

  it("reload перезапрашивает, прежние данные остаются до ответа", async () => {
    const calls = deferredGet();
    const { result } = renderHook(() => useApi<number>("/a"));
    await act(async () => calls[0].resolve(1));
    act(() => result.current.reload());
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(result.current.data).toBe(1);
    await act(async () => calls[1].resolve(2));
    expect(result.current.data).toBe(2);
  });

  it("размонтирование отменяет запрос", () => {
    const calls = deferredGet();
    const { unmount } = renderHook(() => useApi<number>("/a"));
    unmount();
    expect(calls[0].signal?.aborted).toBe(true);
  });
});
