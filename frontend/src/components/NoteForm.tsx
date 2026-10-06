import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { DossierNote } from "../api/types";
import { NOTE_KINDS, PROTOCOL_KINDS } from "../constants/noteKinds";
import { downloadProtocol } from "../utils/protocol";
import { todayIso } from "../utils/date";
import TextArea from "./TextArea";

/** Форма записи индивидуальной работы — одна и та же в карточке студента и в «Моём дне» («Записать» у студента
 * из группы риска): вид, дата, содержание, поля протокола беседы (цель, присутствовавшие, итог) и «вернуться к
 * вопросу». Для беседы, звонка, вызова родителей и договорённости — кнопка «Сохранить и скачать протокол»:
 * запись сохраняется, и сразу скачивается готовый протокол по образцу колледжа. */
export default function NoteForm({
  studentId,
  onSaved,
  onCancel,
  autoFocus,
}: {
  studentId: number;
  /** Запись сохранена (и протокол, если просили, уже скачивается). */
  onSaved: (note: DossierNote | null, withProtocol: boolean) => void;
  /** В окне — кнопка «Отмена». */
  onCancel?: () => void;
  autoFocus?: boolean;
}) {
  const [kind, setKind] = useState("conversation");
  const [text, setText] = useState("");
  const [occurredOn, setOccurredOn] = useState(todayIso());
  const [followUpOn, setFollowUpOn] = useState("");
  const [goal, setGoal] = useState("");
  const [participants, setParticipants] = useState("");
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Какой кнопкой отправили форму: «Сохранить запись» или «Сохранить и скачать протокол».
  const thenProtocol = useRef(false);
  const withProtocol = PROTOCOL_KINDS.includes(kind);

  async function save(e: FormEvent) {
    e.preventDefault();
    const withDownload = thenProtocol.current && withProtocol;
    thenProtocol.current = false;
    setBusy(true);
    setError(null);
    try {
      const note = await api.post<DossierNote>(`/students/${studentId}/dossier/notes`, {
        kind, text, occurred_on: occurredOn || null, ...(followUpOn ? { follow_up_on: followUpOn } : {}),
        ...(withProtocol && goal.trim() ? { goal } : {}),
        ...(withProtocol && participants.trim() ? { participants } : {}),
        ...(withProtocol && result.trim() ? { result } : {}),
      });
      setText("");
      setGoal("");
      setParticipants("");
      setResult("");
      setFollowUpOn("");
      setOccurredOn(todayIso());
      if (withDownload && note?.id) {
        downloadProtocol(studentId, note).catch((err) =>
          setError(err instanceof ApiError ? err.message : "Запись сохранена, но протокол сформировать не удалось")
        );
      }
      onSaved(note && note.id ? note : null, withDownload);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить запись");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="note-form" onSubmit={save} aria-label="Запись индивидуальной работы">
      <div className="dossier-grid">
        <label className="dossier-field">
          <span className="dossier-field__label">Вид записи</span>
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {Object.entries(NOTE_KINDS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="dossier-field">
          <span className="dossier-field__label">Дата</span>
          <input type="date" value={occurredOn} max={todayIso()} onChange={(e) => setOccurredOn(e.target.value)} />
        </label>
        <label className="dossier-field dossier-field--wide">
          <span className="dossier-field__label">{withProtocol ? "Содержание беседы" : "Что произошло"}</span>
          <TextArea expandTitle="Содержание"
            rows={3}
            placeholder="Что произошло, о чём договорились"
            value={text}
            onChange={(e) => setText(e.target.value)}
            required
            autoFocus={autoFocus}
          />
        </label>
      </div>

      {withProtocol && (
        <div className="note-form__protocol">
          <h5>Для протокола беседы в Word</h5>
          <p className="hint">Необязательно: что не заполнено, в протоколе останется строками для записи от руки.</p>
          <div className="dossier-grid">
            <label className="dossier-field dossier-field--wide">
              <span className="dossier-field__label">Цель беседы</span>
              <input value={goal} maxLength={500} placeholder="Например: выяснить причины пропусков" onChange={(e) => setGoal(e.target.value)} />
            </label>
            <label className="dossier-field dossier-field--wide">
              <span className="dossier-field__label">Присутствовали</span>
              <TextArea expandTitle="Присутствовали" rows={3} value={participants} maxLength={2000} placeholder={"Иванова М. П., мать\nКуратор группы"} onChange={(e) => setParticipants(e.target.value)} />
              <span className="dossier-field__hint">По одному в строке: ФИО, кем приходится или должность</span>
            </label>
            <label className="dossier-field dossier-field--wide">
              <span className="dossier-field__label">Итог беседы</span>
              <TextArea expandTitle="Результат" rows={2} value={result} maxLength={2000} placeholder="О чём договорились, что дальше" onChange={(e) => setResult(e.target.value)} />
            </label>
          </div>
        </div>
      )}

      <div className="dossier-grid">
        <label className="dossier-field">
          <span className="dossier-field__label">Вернуться к вопросу</span>
          <input type="date" value={followUpOn} min={occurredOn || todayIso()} onChange={(e) => setFollowUpOn(e.target.value)} />
          <span className="dossier-field__hint">Необязательно: в этот день запись появится в «Моём дне»</span>
        </label>
      </div>

      {error && <div className="error-text">{error}</div>}

      <div className="dossier-actions">
        {onCancel && (
          <button type="button" className="btn-secondary" onClick={onCancel}>
            Отмена
          </button>
        )}
        <button
          type="submit"
          className={withProtocol ? "btn-secondary" : "btn-primary"}
          disabled={busy}
          onClick={() => (thenProtocol.current = false)}
        >
          Сохранить запись
        </button>
        {withProtocol && (
          <button type="submit" className="btn-primary" disabled={busy} onClick={() => (thenProtocol.current = true)}>
            Сохранить и скачать протокол
          </button>
        )}
      </div>
    </form>
  );
}
