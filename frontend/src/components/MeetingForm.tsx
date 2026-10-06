import { useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { ParentMeeting } from "../api/types";
import { useEscapeKey } from "../hooks/useEscapeKey";

/** Окно родительского собрания: повестка, участники, «слушали / постановили». Из него делается протокол в Word. */
export default function MeetingForm({
  groupId, year, meeting, onSaved, onClose,
}: { groupId: number; year: string; meeting: ParentMeeting | null; onSaved: () => void; onClose: () => void }) {
  const [date, setDate] = useState(meeting?.meeting_date ?? "");
  const [number, setNumber] = useState(meeting ? String(meeting.number) : "");
  const [agenda, setAgenda] = useState(meeting?.agenda ?? "");
  const [staff, setStaff] = useState(meeting?.staff ?? "");
  const [speakers, setSpeakers] = useState(meeting?.speakers ?? "");
  const [format, setFormat] = useState(meeting?.meeting_format ?? "in_person");
  const [count, setCount] = useState(meeting?.parents_count != null ? String(meeting.parents_count) : "");
  const [listened, setListened] = useState(meeting?.listened ?? "");
  const [resolved, setResolved] = useState(meeting?.resolved ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEscapeKey(onClose);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      meeting_date: date || null, number: number ? Number(number) : null, agenda: agenda || null, staff: staff || null,
      speakers: speakers || null, meeting_format: format, parents_count: count === "" ? null : Number(count),
      listened: listened || null, resolved: resolved || null, ...(date ? {} : { school_year: year }),
    };
    try {
      if (meeting) await api.put(`/meetings/${meeting.id}`, body);
      else await api.post(`/meetings/groups/${groupId}`, body);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить собрание");
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal event-form" role="dialog" aria-modal="true" aria-label="Родительское собрание" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <h3>{meeting ? `Родительское собрание №${meeting.number}` : "Новое родительское собрание"}</h3>
        <div className="inline-form form-fields">
          <label>
            Дата проведения
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <label>
            Номер собрания
            <input type="number" min={1} max={99} value={number} placeholder="следующий" onChange={(e) => setNumber(e.target.value)} />
          </label>
        </div>
        <label>
          Повестка (по одному вопросу в строке)
          <textarea rows={3} value={agenda} maxLength={3000} onChange={(e) => setAgenda(e.target.value)} />
        </label>
        <label>
          Присутствовали сотрудники колледжа (по одному в строке: ФИО, должность)
          <textarea rows={2} value={staff} maxLength={2000} onChange={(e) => setStaff(e.target.value)} />
        </label>
        <label>
          Приглашённые спикеры, эксперты (по одному в строке)
          <textarea rows={2} value={speakers} maxLength={2000} onChange={(e) => setSpeakers(e.target.value)} />
        </label>
        <div className="inline-form form-fields">
          <label>
            Формат проведения
            <select value={format} onChange={(e) => setFormat(e.target.value)}>
              <option value="in_person">Очный</option>
              <option value="remote">Дистанционный</option>
            </select>
          </label>
          <label title="Если родителей не отмечали поимённо — число для протокола">
            Родителей присутствовало (число)
            <input type="number" min={0} max={500} value={count} onChange={(e) => setCount(e.target.value)} />
          </label>
        </div>
        <label>
          Слушали
          <textarea rows={3} value={listened} maxLength={5000} onChange={(e) => setListened(e.target.value)} />
        </label>
        <label>
          Постановили
          <textarea rows={3} value={resolved} maxLength={5000} onChange={(e) => setResolved(e.target.value)} />
        </label>
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
