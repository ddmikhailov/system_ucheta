import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api/client";
import { APP_VERSION } from "../constants/release";
import { useEscapeKey } from "../hooks/useEscapeKey";
import { clientContext } from "../utils/clientInfo";
import { toast } from "../utils/feedback";
import TextArea from "./TextArea";

const MAX_LENGTH = 1000;

/** «Сообщить о проблеме»: короткий текст человека, а страницу, версию, браузер и экран интерфейс добавляет сам.
 * Сообщение приходит всем администраторам в колокольчик. */
export default function ProblemReportModal({ onClose }: { onClose: () => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Снимок на момент открытия окна: адрес страницы, где человек столкнулся с проблемой.
  const [context] = useState(() => clientContext(APP_VERSION));
  useEscapeKey(onClose);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const { delivered } = await api.post<{ delivered: number }>("/support/problem-report", { ...context, text: text.trim() });
      if (delivered > 0) {
        toast("Сообщение отправлено администратору");
        onClose();
      } else {
        setError("В платформе сейчас нет активного администратора — сообщите о проблеме по телефону.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить сообщение");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form
        className="modal problem-report"
        role="dialog"
        aria-modal="true"
        aria-labelledby="problem-report-title"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h3 id="problem-report-title">Сообщить о проблеме</h3>
        <label>
          Что случилось?
          <TextArea
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={MAX_LENGTH}
            rows={4}
            autoFocus
            required
            placeholder="Например: нажимаю «Сохранить» в журнале, а отметки не сохраняются"
            expandTitle="Что случилось?"
          />
        </label>
        <div className="problem-report__context">
          <span>К сообщению добавятся:</span>
          <dl>
            <dt>Страница</dt>
            <dd>{context.page}</dd>
            <dt>Версия</dt>
            <dd>{context.version}</dd>
            <dt>Браузер</dt>
            <dd>{context.browser}</dd>
            <dt>Экран</dt>
            <dd>{context.screen}</dd>
          </dl>
        </div>
        {error && (
          <div className="error-text" role="alert">
            {error}
          </div>
        )}
        <div className="problem-report__actions">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Отмена
          </button>
          <button type="submit" className="btn-primary" disabled={busy || !text.trim()}>
            {busy ? "Отправка…" : "Отправить"}
          </button>
        </div>
      </form>
    </div>
  );
}
