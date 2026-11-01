import { useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { SafetyInstruction } from "../api/types";
import { useEscapeKey } from "../hooks/useEscapeKey";
import TextArea from "./TextArea";

/** Окно записи журнала инструктажа по охране труда: дата, вид, тема, кто провёл. Из записи делается бланк для подписей. */
export default function InstructionForm({
  groupId, kinds, record, onSaved, onClose,
}: { groupId: number; kinds: Record<string, string>; record: SafetyInstruction | null; onSaved: () => void; onClose: () => void }) {
  const [date, setDate] = useState(record?.instruction_date ?? "");
  const [kind, setKind] = useState(record?.kind ?? "introductory");
  const [topic, setTopic] = useState(record?.topic ?? "");
  const [by, setBy] = useState(record?.conducted_by ?? "");
  const [note, setNote] = useState(record?.note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEscapeKey(onClose);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = { instruction_date: date, kind, topic, conducted_by: by || null, note: note || null };
    try {
      if (record) await api.put(`/instructions/${record.id}`, body);
      else await api.post(`/instructions/groups/${groupId}`, body);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить запись инструктажа");
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal event-form" role="dialog" aria-modal="true" aria-label="Инструктаж по охране труда" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <h3>{record ? "Запись инструктажа" : "Новая запись инструктажа"}</h3>
        <div className="inline-form form-fields">
          <label>
            Дата инструктажа
            <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <label>
            Вид инструктажа
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              {Object.entries(kinds).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label>
          Тема
          <TextArea expandTitle="Тема инструктажа" rows={2} required value={topic} maxLength={500} onChange={(e) => setTopic(e.target.value)} />
        </label>
        <label>
          Кто провёл (ФИО; пусто — в бланк попадёт куратор группы)
          <input type="text" value={by} maxLength={200} onChange={(e) => setBy(e.target.value)} />
        </label>
        <label>
          Примечание
          <TextArea expandTitle="Примечание" rows={2} value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
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
