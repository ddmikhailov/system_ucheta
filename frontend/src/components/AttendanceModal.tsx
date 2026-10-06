import { useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { GroupEvent, PlanStudent } from "../api/types";
import { useEscapeKey } from "../hooks/useEscapeKey";

/** Кто присутствовал на классном часе (по умолчанию — все, пока отметок ещё не было). Список идёт в протокол. */
export default function AttendanceModal({
  event, students, onSaved, onClose,
}: { event: GroupEvent; students: PlanStudent[]; onSaved: () => void; onClose: () => void }) {
  const [chosen, setChosen] = useState<number[]>(event.attendee_ids.length > 0 ? event.attendee_ids : students.map((s) => s.id));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEscapeKey(onClose);

  const toggle = (id: number) => setChosen((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.put(`/events/${event.id}/attendance`, { student_ids: chosen });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal group-list-modal" role="dialog" aria-modal="true" aria-label="Присутствующие на классном часе" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <h3>Присутствующие: {event.title}</h3>
        <div className="toolbar">
          <button type="button" className="chip" onClick={() => setChosen(students.map((s) => s.id))}>
            Все
          </button>
          <button type="button" className="chip" onClick={() => setChosen([])}>
            Никого
          </button>
          <span className="hint" aria-live="polite">
            Присутствует: {chosen.length} из {students.length}
          </span>
        </div>
        <fieldset className="group-list-fields">
          <legend>Студенты группы</legend>
          {students.map((s) => (
            <label key={s.id}>
              <input type="checkbox" checked={chosen.includes(s.id)} onChange={() => toggle(s.id)} /> {s.full_name}
            </label>
          ))}
        </fieldset>
        {error && <div className="error-text">{error}</div>}
        <div className="actions">
          <button type="submit" disabled={busy}>
            Сохранить
          </button>
          <button type="button" className="link-btn" onClick={onClose}>
            Отмена
          </button>
        </div>
      </form>
    </div>
  );
}
