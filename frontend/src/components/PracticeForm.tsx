import { useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { GroupPractice, PracticeKind } from "../api/types";
import { useEscapeKey } from "../hooks/useEscapeKey";
import { todayIso } from "../utils/date";
import TextArea from "./TextArea";

const KINDS: { key: PracticeKind; label: string }[] = [
  { key: "educational", label: "Учебная" },
  { key: "production", label: "Производственная" },
  { key: "pre_diploma", label: "Преддипломная" },
];

/** Окно практики группы: даты, база, руководители, получение характеристики. После сохранения платформа сама
 * ставит всем студентам группы отметку практики («р») на учебные дни периода. */
export default function PracticeForm({
  groupId, practice, onSaved, onClose,
}: { groupId: number; practice: GroupPractice | null; onSaved: (replacedMarks: number) => void; onClose: () => void }) {
  const [kind, setKind] = useState<PracticeKind>(practice?.kind ?? "production");
  const [dateFrom, setDateFrom] = useState(practice?.date_from ?? "");
  const [dateTo, setDateTo] = useState(practice?.date_to ?? "");
  const [base, setBase] = useState(practice?.base ?? "");
  const [college, setCollege] = useState(practice?.college_supervisor ?? "");
  const [baseSupervisor, setBaseSupervisor] = useState(practice?.base_supervisor ?? "");
  const [phone, setPhone] = useState(practice?.phone ?? "");
  const [received, setReceived] = useState(practice?.review_received ?? false);
  const [receivedOn, setReceivedOn] = useState(practice?.review_received_on ?? "");
  const [note, setNote] = useState(practice?.note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEscapeKey(onClose);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      kind, date_from: dateFrom, date_to: dateTo, base: base || null, college_supervisor: college || null,
      base_supervisor: baseSupervisor || null, phone: phone || null, review_received: received,
      review_received_on: received ? receivedOn || null : null, note: note || null,
    };
    try {
      const saved = practice
        ? await api.put<GroupPractice>(`/practice/${practice.id}`, body)
        : await api.post<GroupPractice>(`/practice/groups/${groupId}`, body);
      onSaved(saved.replaced_marks);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить практику");
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal event-form" role="dialog" aria-modal="true" aria-label="Практика группы" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <h3>{practice ? "Практика группы" : "Новая практика группы"}</h3>
        <p className="hint">Всем студентам группы платформа поставит отметку «р» на учебные дни этого периода.</p>
        <label>
          Вид практики
          <select value={kind} onChange={(e) => setKind(e.target.value as PracticeKind)}>
            {KINDS.map((k) => (
              <option key={k.key} value={k.key}>{k.label}</option>
            ))}
          </select>
        </label>
        <div className="inline-form form-fields">
          <label>
            С даты
            <input type="date" required value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label>
            По дату
            <input type="date" required value={dateTo} min={dateFrom || undefined} onChange={(e) => setDateTo(e.target.value)} />
          </label>
        </div>
        <label>
          База практики (организация)
          <input type="text" value={base} maxLength={255} onChange={(e) => setBase(e.target.value)} />
        </label>
        <div className="inline-form form-fields">
          <label>
            Руководитель от колледжа
            <input type="text" value={college} maxLength={255} onChange={(e) => setCollege(e.target.value)} />
          </label>
          <label>
            Руководитель от базы
            <input type="text" value={baseSupervisor} maxLength={255} onChange={(e) => setBaseSupervisor(e.target.value)} />
          </label>
        </div>
        <label>
          Телефон руководителя
          <input type="tel" value={phone} maxLength={64} onChange={(e) => setPhone(e.target.value)} />
        </label>
        <label className="check-inline">
          <input
            type="checkbox"
            checked={received}
            onChange={(e) => {
              setReceived(e.target.checked);
              if (e.target.checked && !receivedOn) setReceivedOn(todayIso());
            }}
          />{" "}
          Характеристика с места практики получена
        </label>
        {received && (
          <label>
            Дата получения
            <input type="date" value={receivedOn} onChange={(e) => setReceivedOn(e.target.value)} />
          </label>
        )}
        <label>
          Заметка
          <TextArea expandTitle="Заметка о практике" rows={2} value={note} maxLength={3000} onChange={(e) => setNote(e.target.value)} />
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
