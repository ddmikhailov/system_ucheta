import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, downloadFile, getToken, setToken, uploadFile } from "./client";

function respond(status: number, body?: unknown, contentType = "application/json"): Response {
  const text = body === undefined ? "" : typeof body === "string" ? body : JSON.stringify(body);
  return new Response(status === 204 ? null : text, { status, headers: { "Content-Type": contentType } });
}

function mockFetch(response: Response) {
  // Тело Response читается один раз, поэтому на каждый вызов отдаём свежую копию.
  const fn = vi.fn().mockImplementation(async () => response.clone());
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api", () => {
  it("отправляет токен и возвращает JSON", async () => {
    setToken("tok");
    const fetchMock = mockFetch(respond(200, { ok: 1 }));
    expect(await api.get<{ ok: number }>("/x")).toEqual({ ok: 1 });
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBe("Bearer tok");
  });

  it("не отправляет заголовок авторизации без токена", async () => {
    const fetchMock = mockFetch(respond(200, {}));
    await api.get("/x");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBeUndefined();
  });

  it("ответ 204 даёт undefined", async () => {
    mockFetch(respond(204));
    expect(await api.delete("/x")).toBeUndefined();
  });

  it("ошибку берёт из поля detail", async () => {
    mockFetch(respond(400, { detail: "Нельзя отправить" }));
    await expect(api.post("/x", {})).rejects.toMatchObject({ status: 400, message: "Нельзя отправить" });
    await expect(api.post("/x", {})).rejects.toBeInstanceOf(ApiError);
  });

  it("при не-JSON теле ошибки оставляет statusText", async () => {
    mockFetch(new Response("<html>", { status: 502, statusText: "Bad Gateway" }));
    await expect(api.get("/x")).rejects.toMatchObject({ status: 502, message: "Bad Gateway" });
  });

  it("401 стирает токен и сообщает приложению", async () => {
    setToken("tok");
    const listener = vi.fn();
    window.addEventListener("auth:unauthorized", listener);
    mockFetch(respond(401, { detail: "Токен недействителен" }));
    await expect(api.get("/x")).rejects.toMatchObject({ status: 401 });
    window.removeEventListener("auth:unauthorized", listener);
    expect(getToken()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("успешный не-JSON ответ — явная ошибка, а не молчаливый Blob", async () => {
    mockFetch(respond(200, "<html>proxy error</html>", "text/html"));
    await expect(api.get("/x")).rejects.toThrow(/Неожиданный тип ответа/);
  });

  it("тело POST сериализуется в JSON, PUT/PATCH тоже", async () => {
    const fetchMock = mockFetch(respond(200, {}));
    await api.post("/x", { a: 1 });
    await api.put("/x", { b: 2 });
    await api.patch("/x", { c: 3 });
    expect(fetchMock.mock.calls.map((c) => [c[1].method, c[1].body])).toEqual([
      ["POST", '{"a":1}'],
      ["PUT", '{"b":2}'],
      ["PATCH", '{"c":3}'],
    ]);
  });
});

describe("uploadFile", () => {
  it("шлёт файл сырым телом с токеном и типом файла", async () => {
    setToken("tok");
    const fetchMock = mockFetch(respond(200, { total: 3 }));
    const file = new File(["data"], "a.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    expect(await uploadFile<{ total: number }>("/dossier-import/preview", file)).toEqual({ total: 3 });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/dossier-import\/preview$/);
    expect(init.method).toBe("POST");
    expect(init.body).toBe(file);
    expect(init.headers["Content-Type"]).toBe(file.type);
    expect(init.headers.Authorization).toBe("Bearer tok");
  });

  it("показывает сообщение сервера при ошибке", async () => {
    mockFetch(respond(413, { detail: "Файл больше 5 МБ" }));
    await expect(uploadFile("/x", new File(["x"], "a.xlsx"))).rejects.toMatchObject({
      status: 413,
      message: "Файл больше 5 МБ",
    });
  });
});

describe("downloadFile", () => {
  it("скачивает файл с токеном и подставляет имя", async () => {
    setToken("tok");
    const fetchMock = mockFetch(new Response("файл", { status: 200, headers: { "Content-Type": "application/octet-stream" } }));
    const click = vi.fn();
    const created: HTMLAnchorElement[] = [];
    const realCreate = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const el = realCreate(tag);
      if (tag === "a") {
        (el as HTMLAnchorElement).click = click;
        created.push(el as HTMLAnchorElement);
      }
      return el;
    });
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    await downloadFile("/students/1/absence-sheet?date_from=a", "лист.docx");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer tok");
    expect(click).toHaveBeenCalledTimes(1);
    expect(created[0].download).toBe("лист.docx");
    vi.restoreAllMocks();
  });

  it("при ошибке показывает сообщение сервера, а не statusText", async () => {
    mockFetch(respond(400, { detail: "За выбранный период у студента нет пропусков и опозданий" }));
    await expect(downloadFile("/x", "f.docx")).rejects.toMatchObject({
      status: 400, message: "За выбранный период у студента нет пропусков и опозданий",
    });
  });

  it("не-JSON тело ошибки — statusText", async () => {
    mockFetch(new Response("<html>", { status: 502, statusText: "Bad Gateway" }));
    await expect(downloadFile("/x", "f.docx")).rejects.toMatchObject({ status: 502, message: "Bad Gateway" });
  });
});
