// Диалоги подтверждения/ввода и всплывающие сообщения, нарисованные самим приложением, вместо
// window.confirm/prompt: системные окна выглядят чужими, на телефоне перекрывают экран и не
// объясняют последствия. Компонент FeedbackHost (монтируется один раз в App) подписывается на
// очередь и показывает их. Вызовы идут через объект `dialogs`, чтобы тесты могли подменить
// ответ: vi.spyOn(dialogs, "confirm").mockResolvedValue(true).

export interface ConfirmOptions {
  /** Текст основной кнопки, по умолчанию «Да». Лучше глагол: «Удалить», «Сменить группу». */
  confirmLabel?: string;
  cancelLabel?: string;
  /** Опасное действие: основная кнопка красная. */
  danger?: boolean;
}

export interface PromptOptions {
  confirmLabel?: string;
  /** Поле только для чтения: показать текст, чтобы его скопировали (например, ссылку). */
  readOnly?: boolean;
}

export type DialogRequest =
  | { id: number; kind: "confirm"; message: string; options: ConfirmOptions; resolve: (ok: boolean) => void }
  | {
      id: number;
      kind: "prompt";
      message: string;
      defaultValue: string;
      options: PromptOptions;
      resolve: (value: string | null) => void;
    };

export type ToastKind = "ok" | "error" | "info";

export interface Toast {
  id: number;
  message: string;
  kind: ToastKind;
}

interface State {
  dialog: DialogRequest | null;
  toasts: Toast[];
}

let state: State = { dialog: null, toasts: [] };
let nextId = 1;
const listeners = new Set<(s: State) => void>();
const queue: DialogRequest[] = [];

function emit() {
  for (const l of listeners) l(state);
}

function showNextDialog() {
  if (state.dialog || queue.length === 0) return;
  state = { ...state, dialog: queue.shift()! };
  emit();
}

export function subscribeFeedback(listener: (s: State) => void): () => void {
  listeners.add(listener);
  listener(state);
  return () => {
    listeners.delete(listener);
  };
}

/** Закрыть текущий диалог (вызывается хостом после ответа). */
export function settleDialog() {
  state = { ...state, dialog: null };
  emit();
  showNextDialog();
}

function confirm(message: string, options: ConfirmOptions = {}): Promise<boolean> {
  // Хост не смонтирован (отдельный компонент в тесте, сбой рендера) — не зависаем навсегда.
  if (listeners.size === 0) return Promise.resolve(window.confirm(message));
  return new Promise((resolve) => {
    queue.push({ id: nextId++, kind: "confirm", message, options, resolve });
    showNextDialog();
  });
}

function prompt(message: string, defaultValue = "", options: PromptOptions = {}): Promise<string | null> {
  if (listeners.size === 0) return Promise.resolve(window.prompt(message, defaultValue));
  return new Promise((resolve) => {
    queue.push({ id: nextId++, kind: "prompt", message, defaultValue, options, resolve });
    showNextDialog();
  });
}

export const dialogs = { confirm, prompt };

const TOAST_MS = 4500;

/** Короткое сообщение о результате действия внизу экрана — видно, даже если страница прокручена. */
export function toast(message: string, kind: ToastKind = "ok") {
  const item: Toast = { id: nextId++, message, kind };
  state = { ...state, toasts: [...state.toasts.slice(-2), item] };
  emit();
  window.setTimeout(() => dismissToast(item.id), kind === "error" ? TOAST_MS * 2 : TOAST_MS);
}

export function dismissToast(id: number) {
  if (!state.toasts.some((t) => t.id === id)) return;
  state = { ...state, toasts: state.toasts.filter((t) => t.id !== id) };
  emit();
}

/** Только для тестов: сбросить очередь между тестами. */
export function resetFeedback() {
  queue.length = 0;
  state = { dialog: null, toasts: [] };
  emit();
}
