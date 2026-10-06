import { useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { GroupEvent, PlanSection } from "../api/types";
import { EVENT_STATUSES } from "../constants/eventStatuses";
import { useEscapeKey } from "../hooks/useEscapeKey";

/** Окно мероприятия плана воспитательной работы: создание и правка. Классный час — мероприятие с отметкой
 * присутствующих, из него делается протокол (Word). */
export default function EventForm({
  groupId, year, sections, event, defaultSection, onSaved, onClose,
}: {
  groupId: number;
  year: string;
  sections: PlanSection[];
  event: GroupEvent | null;
  defaultSection: string;
  onSaved: () => void;
  onClose: () => void;
}) {
  const [section, setSection] = useState(event?.section ?? defaultSection);
  const [title, setTitle] = useState(event?.title ?? "");
  const [date, setDate] = useState(event?.event_date ?? "");
  const [time, setTime] = useState(event?.time_text ?? "");
  const [responsible, setResponsible] = useState(event?.responsible ?? "");
  const [goal, setGoal] = useState(event?.goal ?? "");
  const [status, setStatus] = useState(event?.status ?? "planned");
  const [result, setResult] = useState(event?.result ?? "");
  const [classHour, setClassHour] = useState(event?.is_class_hour ?? false);
  const [description, setDescription] = useState(event?.description ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEscapeKey(onClose);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      section, title, event_date: date || null, time_text: time || null, responsible: responsible || null,
      goal: goal || null, status, result: result || null, is_class_hour: classHour,
      description: classHour ? description || null : null, ...(date ? {} : { school_year: year }),
    };
    try {
      if (event) await api.put(`/events/${event.id}`, body);
      else await api.post(`/events/groups/${groupId}`, body);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить мероприятие");
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal event-form" role="dialog" aria-modal="true" aria-label="Мероприятие плана" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <h3>{event ? "Мероприятие плана" : "Новое мероприятие"}</h3>
        <label>
          Раздел плана
          <select value={section} onChange={(e) => setSection(e.target.value)}>
            {sections.map((s) => (
              <option key={s.key} value={s.key}>
                {s.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Наименование мероприятия
          <input value={title} maxLength={500} required onChange={(e) => setTitle(e.target.value)} />
        </label>
        <div className="inline-form form-fields">
          <label>
            Дата
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <label>
            Время
            <input value={time} maxLength={32} placeholder="14:30 или 1 пара" onChange={(e) => setTime(e.target.value)} />
          </label>
        </div>
        <label>
          Ответственные за проведение
          <input value={responsible} maxLength={255} onChange={(e) => setResponsible(e.target.value)} />
        </label>
        <label>
          Цель мероприятия (формируемые компетенции, задачи)
          <textarea rows={2} value={goal} maxLength={2000} onChange={(e) => setGoal(e.target.value)} />
        </label>
        <label>
          Отметка о выполнении
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {Object.entries(EVENT_STATUSES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {status !== "planned" && (
          <label>
            Результат (краткий анализ, вывод)
            <textarea rows={2} value={result} maxLength={2000} onChange={(e) => setResult(e.target.value)} />
          </label>
        )}
        <label className="inline-check">
          <input type="checkbox" checked={classHour} onChange={(e) => setClassHour(e.target.checked)} /> Классный час
        </label>
        <p className="hint">У классного часа можно отметить присутствующих и получить протокол в Word.</p>
        {classHour && (
          <label>
            Формат и описание проведения (для протокола)
            <textarea rows={3} value={description} maxLength={3000} onChange={(e) => setDescription(e.target.value)} />
          </label>
        )}
        {error && <div className="error-text">{error}</div>}
        <div className="actions">
          <button type="submit" disabled={busy || !title.trim()}>
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
