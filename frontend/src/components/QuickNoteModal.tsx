import { useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api/client";
import { NOTE_KINDS } from "../constants/noteKinds";
import { useEscapeKey } from "../hooks/useEscapeKey";
import { todayIso } from "../utils/date";

/** Быстрая запись об индивидуальной работе (беседа, звонок, вызов родителей…) без захода в карточку студента.
 * Пишет обычную заметку досье с датой «сегодня» и необязательным сроком «вернуться к вопросу». */
export default function QuickNoteModal({
  studentId,
  studentName,
  onSaved,
  onClose,
}: {
  studentId: number;
  studentName: string;
  onSaved: () => void;
  onClose: () => void;
}) {
  const [kind, setKind] = useState("conversation");
  const [text, setText] = useState("");
  const [followUpOn, setFollowUpOn] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEscapeKey(onClose);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post(`/students/${studentId}/dossier/notes`, {
        kind,
        text,
        occurred_on: todayIso(),
        ...(followUpOn ? { follow_up_on: followUpOn } : {}),
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить запись");
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Быстрая запись"
        onClick={(e) => e.stopPropagation()}
        onSubmit={save}
      >
        <h3>Запись: {studentName}</h3>
        <label>
          Вид записи
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {Object.entries(NOTE_KINDS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Что было сделано
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} required autoFocus />
        </label>
        <label>
          Вернуться к вопросу (необязательно)
          <input type="date" value={followUpOn} min={todayIso()} onChange={(e) => setFollowUpOn(e.target.value)} />
        </label>
        {error && <div className="error-text">{error}</div>}
        <div className="actions">
          <button type="button" onClick={onClose}>
            Отмена
          </button>
          <button type="submit" disabled={busy || !text.trim()}>
            Сохранить
          </button>
        </div>
      </form>
    </div>
  );
}
