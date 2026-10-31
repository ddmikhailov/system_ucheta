import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { PdChange } from "../api/types";
import { formatServerDateTime, todayIso } from "../utils/date";

/** «Изменение ПДн за месяц» (п. 3.1.15 положения): кто и когда менял ФИО, контакты, адреса и другие данные студента.
 * Администратор сверяет список и сообщает в отдел кадров. Значения не показываются — только названия полей. */
export default function PdChangesList() {
  const [month, setMonth] = useState(todayIso().slice(0, 7));
  const [rows, setRows] = useState<PdChange[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<PdChange[]>(`/admin/pd-changes?month=${month}-01`)
      .then((r) => {
        setRows(Array.isArray(r) ? r : []);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить изменения ПДн"));
  }, [month]);

  return (
    <section className="add-block" aria-label="Изменение ПДн за месяц">
      <p className="add-block__title">Изменение ПДн студентов за месяц</p>
      <label>
        Месяц
        <input type="month" value={month} onChange={(e) => {
            if (!e.target.value) return;
            setRows(null);
            setMonth(e.target.value);
          }} />
      </label>
      {error && <div className="error-text">{error}</div>}
      {rows && rows.length === 0 && <p className="hint">За этот месяц изменений нет.</p>}
      {rows && rows.length > 0 && (
        <table className="roster-table">
          <thead>
            <tr>
              <th>Когда</th>
              <th>Студент</th>
              <th>Что изменено</th>
              <th>Кто</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td data-label="Когда">{formatServerDateTime(r.created_at)}</td>
                <td data-label="Студент">
                  <Link to={`/students/${r.student_id}`}>{r.student_name}</Link> · {r.group_code}
                </td>
                <td data-label="Что изменено">{r.changes.join(", ")}</td>
                <td data-label="Кто">{r.changed_by_name ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
