import { useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { MeetingGuardian, ParentMeeting } from "../api/types";
import { useEscapeKey } from "../hooks/useEscapeKey";

/** Кто из родителей / законных представителей пришёл на собрание: список идёт в регистрацию протокола. */
export default function ParentsAttendanceModal({
  meeting, guardians, onSaved, onClose,
}: { meeting: ParentMeeting; guardians: MeetingGuardian[]; onSaved: () => void; onClose: () => void }) {
  const [chosen, setChosen] = useState<number[]>(meeting.attendee_ids);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEscapeKey(onClose);

  const toggle = (id: number) => setChosen((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.put(`/meetings/${meeting.id}/attendance`, { guardian_ids: chosen });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal group-list-modal" role="dialog" aria-modal="true" aria-label="Присутствующие родители" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <h3>Присутствующие родители: собрание №{meeting.number}</h3>
        {guardians.length === 0 ? (
          <p className="hint">В досье студентов группы нет представителей — число родителей можно указать в самом собрании.</p>
        ) : (
          <>
            <div className="toolbar">
              <button type="button" className="chip" onClick={() => setChosen([])}>
                Снять все
              </button>
              <span className="hint" aria-live="polite">
                Отмечено: {chosen.length} из {guardians.length}
              </span>
            </div>
            <fieldset className="group-list-fields">
              <legend>Представители студентов группы</legend>
              {guardians.map((g) => (
                <label key={g.id}>
                  <input type="checkbox" checked={chosen.includes(g.id)} onChange={() => toggle(g.id)} /> {g.full_name}
                  <span className="hint">
                    {" "}
                    — {g.relation}, {g.student_name}
                  </span>
                </label>
              ))}
            </fieldset>
          </>
        )}
        {error && <div className="error-text">{error}</div>}
        <div className="actions">
          <button type="submit" disabled={busy || guardians.length === 0}>
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
