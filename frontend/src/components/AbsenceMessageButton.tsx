import { useState } from "react";
import TextArea from "./TextArea";
import { api, ApiError } from "../api/client";
import type { AbsenceMessage } from "../api/types";

/** «Сообщение родителям о пропусках»: платформа готовит текст по журналу, куратор копирует его в мессенджер
 * (отправки из платформы нет). Если браузер не даёт доступ к буферу обмена, текст остаётся в поле — его можно
 * скопировать вручную. */
export default function AbsenceMessageButton({ studentId, days = 14 }: { studentId: number; days?: number }) {
  const [message, setMessage] = useState<AbsenceMessage | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function prepare() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const m = await api.get<AbsenceMessage>(`/students/${studentId}/absence-message?days=${days}`);
      setMessage(m);
      if (!m.text) {
        setNotice(`За последние ${m.days} дн. нет пропусков без уважительной причины — сообщать нечего.`);
        return;
      }
      try {
        await navigator.clipboard.writeText(m.text);
        setNotice("Текст скопирован — вставьте его в мессенджер.");
      } catch {
        setNotice("Не удалось скопировать автоматически — выделите текст ниже и скопируйте вручную.");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось подготовить сообщение");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="absence-message">
      <button onClick={prepare} disabled={busy}>
        Сообщение родителям о пропусках
      </button>
      {error && <div className="error-text">{error}</div>}
      {notice && <p className="hint">{notice}</p>}
      {message?.text && (
        <TextArea className="absence-message__text" expandTitle="Сообщение родителям о пропусках" readOnly rows={8} value={message.text} aria-label="Текст сообщения родителям" />
      )}
    </div>
  );
}
