import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { dismissToast, settleDialog, subscribeFeedback } from "../utils/feedback";
import type { DialogRequest, Toast } from "../utils/feedback";

function Dialog({ request }: { request: DialogRequest }) {
  const [value, setValue] = useState(request.kind === "prompt" ? request.defaultValue : "");
  const inputRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const readOnly = request.kind === "prompt" && request.options.readOnly;

  useEffect(() => {
    if (request.kind === "prompt") {
      inputRef.current?.focus();
      inputRef.current?.select();
    } else {
      confirmRef.current?.focus();
    }
  }, [request]);

  function answer(ok: boolean) {
    if (request.kind === "confirm") request.resolve(ok);
    else request.resolve(ok ? value : null);
    settleDialog();
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        answer(false);
      }
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    answer(true);
  }

  const danger = request.kind === "confirm" && request.options.danger;
  const confirmLabel = request.options.confirmLabel ?? (readOnly ? "Готово" : request.kind === "prompt" ? "Сохранить" : "Да");
  const cancelLabel = request.kind === "confirm" ? (request.options.cancelLabel ?? "Отмена") : "Отмена";

  return (
    <div className="modal-backdrop feedback-backdrop" onClick={() => answer(false)}>
      <form
        className="modal feedback-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={`feedback-${request.id}`}
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <p id={`feedback-${request.id}`} className="feedback-dialog__message">
          {request.message}
        </p>
        {request.kind === "prompt" && (
          <input
            ref={inputRef}
            value={value}
            readOnly={readOnly}
            aria-labelledby={`feedback-${request.id}`}
            onChange={(e) => setValue(e.target.value)}
          />
        )}
        <div className="feedback-dialog__actions">
          {!readOnly && (
            <button type="button" className="btn-secondary" onClick={() => answer(false)}>
              {cancelLabel}
            </button>
          )}
          <button
            ref={confirmRef}
            type="submit"
            className={danger ? "btn-danger" : "btn-primary"}
            disabled={request.kind === "prompt" && !readOnly && !value.trim()}
          >
            {confirmLabel}
          </button>
        </div>
      </form>
    </div>
  );
}

function ToastItem({ toast }: { toast: Toast }) {
  return (
    <div className={`toast toast--${toast.kind}`} role={toast.kind === "error" ? "alert" : "status"}>
      <span>{toast.message}</span>
      <button type="button" className="toast__close" aria-label="Скрыть сообщение" onClick={() => dismissToast(toast.id)}>
        ×
      </button>
    </div>
  );
}

/** Один на приложение: показывает диалоги из dialogs.confirm/prompt и сообщения toast(). */
export default function FeedbackHost() {
  const [dialog, setDialog] = useState<DialogRequest | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(
    () =>
      subscribeFeedback((s) => {
        setDialog(s.dialog);
        setToasts(s.toasts);
      }),
    []
  );

  return (
    <>
      {dialog && <Dialog key={dialog.id} request={dialog} />}
      <div className="toast-stack" aria-live="polite">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} />
        ))}
      </div>
    </>
  );
}
