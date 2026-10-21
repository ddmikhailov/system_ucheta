import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { CompensationOverview, CompensationStudent } from "../api/types";
import { formatDateRu } from "../utils/date";
import { formatPercent } from "../utils/percent";
import TextArea from "./TextArea";

/** «Восполнить пропуски» (решение 21.10.2026): кто в группе пропустил учебный процесс по уважительной причине
 * и должен догнать программу. Куратор сам закрывает студента комментарием — как восполнены пропуски. Практика
 * и ИУП сюда не попадают; студенты с прогулами — в группе риска («Индивидуальная работа»). */
export default function CompensationPanel({ groupId, onChanged }: { groupId: number; onChanged?: () => void }) {
  const [data, setData] = useState<CompensationOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [closing, setClosing] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [showClosed, setShowClosed] = useState(false);

  const load = useCallback(() => {
    api
      .get<CompensationOverview>(`/curator/groups/${groupId}/compensation`)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить «Восполнить пропуски»"));
  }, [groupId]);

  useEffect(load, [load]);

  function startClosing(studentId: number) {
    setClosing(studentId);
    setComment("");
    setError(null);
  }

  async function close(studentId: number) {
    if (!comment.trim()) {
      setError("Напишите, как восполнены пропуски");
      return;
    }
    setSaving(true);
    try {
      await api.post(`/curator/groups/${groupId}/compensation/${studentId}`, { comment: comment.trim() });
      setClosing(null);
      setComment("");
      load();
      onChanged?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось закрыть");
    } finally {
      setSaving(false);
    }
  }

  if (!data) return error ? <div className="error-text">{error}</div> : null;
  if (data.students.length === 0 && data.closed.length === 0) return null;

  return (
    <section className={`compensation-panel${data.students.length > 0 ? " is-active" : ""}`} aria-label="Восполнить пропуски">
      <h3 className="compensation-panel__title">
        Восполнить пропуски{data.students.length > 0 && <span className="compensate-badge">{data.students.length}</span>}
      </h3>
      <p className="hint">
        Студенты пропустили учебный процесс по уважительной причине (больничный, заявление, приказ) и должны догнать программу.
        Когда пропуски восполнены — закройте с комментарием. Практика и ИУП сюда не попадают.
      </p>
      {error && <div className="error-text">{error}</div>}
      {data.students.length === 0 ? (
        <p className="hint">Сейчас никому в группе не нужно восполнять пропуски.</p>
      ) : (
        <ul className="compensation-list">
          {data.students.map((s) => (
            <li key={s.student_id} className="compensation-item">
              <div className="compensation-item__head">
                <Link to={`/students/${s.student_id}`} className="link-btn">
                  {s.full_name}
                </Link>
                {closing !== s.student_id && (
                  <button type="button" className="btn-secondary" onClick={() => startClosing(s.student_id)}>
                    Закрыть
                  </button>
                )}
              </div>
              <div className="compensation-item__meta">{describe(s)}</div>
              {closing === s.student_id && (
                <div className="compensation-item__form">
                  <label className="form-field">
                    Как восполнены пропуски
                    <TextArea
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      maxLength={1000}
                      rows={2}
                      autoFocus
                      expandTitle="Как восполнены пропуски"
                      placeholder="Например: сдал конспекты и тест по пропущенным темам"
                    />
                  </label>
                  <span className="journal__tools">
                    <button type="button" className="btn-primary" disabled={saving} onClick={() => close(s.student_id)}>
                      {saving ? "Сохраняем…" : "Закрыть"}
                    </button>
                    <button type="button" className="btn-secondary" disabled={saving} onClick={() => setClosing(null)}>
                      Отмена
                    </button>
                  </span>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {data.closed.length > 0 && (
        <>
          <button type="button" className="link-btn" aria-expanded={showClosed} onClick={() => setShowClosed((v) => !v)}>
            {showClosed ? "Скрыть закрытые" : `Закрыто в этом семестре: ${data.closed.length}`}
          </button>
          {showClosed && (
            <ul className="compensation-list compensation-list--closed">
              {data.closed.map((c, i) => (
                <li key={`${c.student_id}-${c.closed_on}-${i}`} className="compensation-item">
                  <div className="compensation-item__head">
                    <span>{c.full_name}</span>
                    <span className="hint">
                      {formatDateRu(c.closed_on)}
                      {c.author_name ? ` · ${c.author_name}` : ""}
                    </span>
                  </div>
                  <div className="compensation-item__meta">{c.comment}</div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

function describe(s: CompensationStudent): string {
  const marks = s.by_mark.map((m) => `${m.name.toLowerCase()} — ${m.count}`).join(", ");
  const parts = [`посещаемость ${formatPercent(s.attendance_percent)}`, `пропущено ${s.absent_to_compensate} из ${s.days} дн.`];
  if (marks) parts.push(marks);
  if (s.last_closed_on) parts.push(`после закрытия ${formatDateRu(s.last_closed_on)} — новые пропуски`);
  return parts.join("; ");
}
