import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { formatServerDateTimeFull } from "../../utils/date";
import type { DossierAccessEntry } from "../../api/types";

export function AccessLog({ studentId }: { studentId: number }) {
  const [rows, setRows] = useState<DossierAccessEntry[] | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    api
      .get<DossierAccessEntry[]>(`/students/${studentId}/dossier/access-log`)
      .then(setRows)
      .catch(() => setRows([]));
  }, [open, studentId]);

  return (
    <>
      <h3 className="student-card__section">Журнал просмотров досье</h3>
      {!open ? (
        <button className="link-btn" onClick={() => setOpen(true)}>
          Показать
        </button>
      ) : rows === null ? (
        <p className="hint">Загрузка…</p>
      ) : rows.length === 0 ? (
        <p className="hint">Просмотров нет.</p>
      ) : (
        <table className="dash-table">
          <thead>
            <tr>
              <th>Когда</th>
              <th>Кто</th>
              <th>Особые поля</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td data-label="Когда">{formatServerDateTimeFull(r.created_at)}</td>
                <td data-label="Кто">{r.user_name}</td>
                <td data-label="Особые поля">{r.included_special ? "показаны" : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
