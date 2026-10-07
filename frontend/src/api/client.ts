// В проде фронтенд и API отдаются одним процессом с одного origin — путь
// пустой (относительные запросы). В локальной разработке (frontend на 5173,
// backend на 8000 — два разных процесса) нужен явный адрес backend.
const API_BASE = import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

// Сессия — HttpOnly-cookie, которую ставит сервер: скрипту (и потенциальному XSS) токен недоступен.
// Раньше токен лежал в localStorage под этим ключом; при запуске стираем остаток от прежней версии.
try {
  localStorage.removeItem("kait20_token");
} catch {
  // хранилище недоступно (приватный режим) — нечего чистить
}

// Заголовок защиты от CSRF: сервер требует его для изменяющих запросов с cookie; чужая
// страница не может его добавить без CORS-preflight, который сервер отклоняет.
const CSRF_HEADERS = { "X-Requested-With": "kait20" };
// В разработке frontend и backend на разных портах — cookie нужно передавать явно.
const CREDENTIALS: RequestCredentials = import.meta.env.DEV ? "include" : "same-origin";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...CSRF_HEADERS,
    ...(options.headers as Record<string, string> | undefined),
  };

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: CREDENTIALS });

  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = body.detail ?? message;
    } catch {
      // тело не JSON — оставляем statusText
    }
    if (res.status === 401) {
      // client.ts — не React-компонент и не может дёрнуть useAuth() напрямую;
      // AuthContext слушает это событие и сбрасывает user, чтобы роутер
      // тут же увёл на /login, а не оставлял "залогиненного" с 401 на
      // каждом запросе (см. TODO.md 4 — раньше токен просто стирался).
      window.dispatchEvent(new Event("auth:unauthorized"));
    }
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return undefined as T;

  // Раньше не-JSON ответ молча превращался в Blob и приводился к типу T
  // (см. TODO.md 5) — ни один вызов api.* в приложении блоб не ждёт, так что
  // это маскировало реальную проблему (например, HTML-страницу ошибки от
  // прокси) непонятной ошибкой ниже по стеку вместо явной здесь.
  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new ApiError(res.status, `Неожиданный тип ответа: ${contentType || "не указан"}`);
  }
  return res.json();
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  put: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: <T,>(path: string) => request<T>(path, { method: "DELETE" }),
};

export async function downloadFile(path: string, filename: string) {
  const res = await fetch(`${API_BASE}${path}`, { headers: CSRF_HEADERS, credentials: CREDENTIALS });
  if (!res.ok) {
    // Сервер объясняет отказ в теле ({"detail": "..."}), например «за период нет пропусков».
    let message = res.statusText;
    try {
      message = (await res.json()).detail ?? message;
    } catch {
      // тело не JSON — оставляем statusText
    }
    throw new ApiError(res.status, message);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  // Отзыв сразу после click() в части браузеров обрывает ещё идущее
  // скачивание (см. TODO.md 5) — даём событию клика и старту загрузки
  // отработать первыми.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Загрузка файла сырым телом запроса (не multipart): так бэкенду не нужна лишняя зависимость.
export async function uploadFile<T>(path: string, file: File): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": file.type || "application/octet-stream",
    ...CSRF_HEADERS,
  };
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", headers, body: file, credentials: CREDENTIALS });
  if (!res.ok) {
    let message = res.statusText;
    try {
      message = (await res.json()).detail ?? message;
    } catch {
      // тело не JSON — оставляем statusText
    }
    throw new ApiError(res.status, message);
  }
  return res.json();
}
