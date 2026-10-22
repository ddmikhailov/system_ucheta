import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { DeleteResult, StudentDeletionRequest } from "../api/types";
import { formatDateRu } from "../utils/date";
import { dialogs } from "../utils/feedback";

/** Запросы кураторов на полное удаление студентов — решает админ или зав. отделением. Пусто — блока нет. */
export default function DeletionReviewList() {
  const [items, setItems] = useState<StudentDeletionRequest[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api
      .get<StudentDeletionRequest[]>("/student-deletions")
      .then((rows) => setItems(Array.isArray(rows) ? rows : []))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить запросы на удаление"));
  }, []);

  useEffect(load, [load]);

  async function approve(r: StudentDeletionRequest) {
    if (!(await dialogs.confirm(`Удалить студента «${r.student_name}» навсегда вместе с отметками и историей? Это необратимо.`, { confirmLabel: "Удалить", danger: true }))) return;
    setBusy(true);
    try {
      const res = await api.post<DeleteResult>(`/student-deletions/${r.id}/approve`, {});
      setNotice(res.detail);
      setError(null);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось удалить");
    } finally {
      setBusy(false);
    }
  }

  async function reject(r: StudentDeletionRequest) {
    setBusy(true);
    try {
      await api.post(`/student-deletions/${r.id}/reject`, {});
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось отклонить");
    } finally {
      setBusy(false);
    }
  }

  if (items.length === 0 && !error && !notice) return null;
  return (
    <section className="change-review" aria-label="Запросы на удаление студентов">
      {items.length > 0 && (
        <h3>
          Запросы на удаление студентов <span className="tabbar__badge">{items.length}</span>
        </h3>
      )}
      {notice && <div className="notice">{notice}</div>}
      {error && <div className="error-text">{error}</div>}
      <div className="change-review__list">
        {items.map((r) => (
          <div key={r.id} className="add-block">
            <p className="add-block__title">
              {r.student_name} · {r.group_code}
            </p>
            <p className="hint">
              {r.requested_by_name}, {formatDateRu(r.created_at.slice(0, 10))}: {r.reason}
            </p>
            <div className="actions">
              <button className="danger-btn" onClick={() => approve(r)} disabled={busy}>
                Удалить навсегда
              </button>
              <button onClick={() => reject(r)} disabled={busy}>
                Отклонить
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
