import { ApiError, api } from "../api/client";
import { APP_VERSION } from "../constants/release";
import { clientContext } from "./clientInfo";

// Ошибки JavaScript в браузере уходят на сервер (журнал и Sentry): раньше о белом экране или «мёртвой» кнопке
// узнавали только со слов кураторов. Ошибки ответов сервера (ApiError) не шлём — сервер видит их сам.

const MAX_PER_PAGE_LOAD = 5;
const sent = new Set<string>();

/** Сколько различных ошибок уже отправлено — только для тестов. */
export function resetErrorReporting() {
  sent.clear();
}

function describe(error: unknown): { message: string; stack: string } | null {
  if (error instanceof ApiError) return null;
  if (error instanceof Error) return { message: `${error.name}: ${error.message}`, stack: error.stack ?? "" };
  if (typeof error === "string") return { message: error, stack: "" };
  return null;
}

export function reportClientError(error: unknown) {
  const described = describe(error);
  if (!described || sent.has(described.message) || sent.size >= MAX_PER_PAGE_LOAD) return;
  sent.add(described.message);
  api
    .post("/support/client-error", {
      ...clientContext(APP_VERSION),
      message: described.message.slice(0, 500),
      stack: described.stack.slice(0, 4000),
    })
    // Отправить не удалось (нет сети, сессия кончилась) — молча: сообщение об ошибке не должно порождать новую.
    .catch(() => undefined);
}

/** Подписка на необработанные ошибки страницы; возвращает отписку. */
export function installErrorReporting(): () => void {
  const onError = (e: ErrorEvent) => reportClientError(e.error ?? e.message);
  const onRejection = (e: PromiseRejectionEvent) => reportClientError(e.reason);
  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onRejection);
  return () => {
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onRejection);
  };
}
