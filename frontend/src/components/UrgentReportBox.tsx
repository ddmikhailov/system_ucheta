import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { UrgentReport } from "../api/types";
import { URGENT_CATEGORIES } from "../constants/urgentReport";
import { formatDateRu } from "../utils/date";
import { dialogs } from "../utils/feedback";
import TextArea from "./TextArea";

/** «Сообщить заведующему» (п. 3.1.26 положения о кураторе): куратор сразу сообщает о проступке, правонарушении или ЧП.
 * Заведующий и воспитательный отдел получают уведомление без текста; текст читают в журнале группы. Автор видит,
 * принято ли сообщение, но свой текст после отправки не получает обратно. */
export default function UrgentReportBox({ studentId }: { studentId: number }) {
  const [reports, setReports] = useState<UrgentReport[]>([]);
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<UrgentReport["category"]>("misconduct");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api
      .get<UrgentReport[]>(`/urgent-reports/for-student/${studentId}`)
      .then((rows) => setReports(Array.isArray(rows) ? rows : []))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить сообщения"));
  }, [studentId]);

  useEffect(load, [load]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!(await dialogs.confirm("Отправить срочное сообщение заведующему отделением и воспитательному отделу?", { confirmLabel: "Отправить" }))) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/urgent-reports", { student_id: studentId, category, text });
      setText("");
      setOpen(false);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось отправить сообщение");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="add-block" aria-label="Срочное сообщение заведующему">
      <p className="add-block__title">Срочное сообщение заведующему</p>
      {!open ? (
        <button className="danger-btn" onClick={() => setOpen(true)}>
          Сообщить заведующему
        </button>
      ) : (
        <form onSubmit={send}>
          <p className="hint">О проступке, правонарушении или ЧП. Текст увидят только заведующий и воспитательный отдел отделения.</p>
          <label>
            Что случилось
            <select value={category} onChange={(e) => setCategory(e.target.value as UrgentReport["category"])}>
              {Object.entries(URGENT_CATEGORIES).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <TextArea aria-label="Текст сообщения" expandTitle="Текст сообщения" value={text} onChange={(e) => setText(e.target.value)} minLength={3} maxLength={2000} required />
          <div className="actions">
            <button type="submit" className="danger-btn" disabled={busy}>
              Отправить
            </button>
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)} disabled={busy}>
              Отмена
            </button>
          </div>
        </form>
      )}
      {error && <div className="error-text">{error}</div>}
      {reports.length > 0 && (
        <ul className="hint">
          {reports.map((r) => (
            <li key={r.id}>
              {formatDateRu(r.created_at.slice(0, 10))} · {URGENT_CATEGORIES[r.category]} ·{" "}
              {r.acknowledged_at ? `принял(а) ${r.acknowledged_by_name}` : "ждёт приёма"}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
