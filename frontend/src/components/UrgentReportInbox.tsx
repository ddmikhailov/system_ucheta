import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { UrgentReport } from "../api/types";
import { formatDateRu } from "../utils/date";
import { URGENT_CATEGORIES } from "../constants/urgentReport";

/** Срочные сообщения кураторов о студентах (п. 3.1.26): их читает заведующий отделением, тьютор, воспитательный отдел
 * (своего отделения) и администратор. Пока нет непринятых — блока нет. Открытие списка пишется в журнал действий. */
export default function UrgentReportInbox() {
  const [items, setItems] = useState<UrgentReport[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api
      .get<UrgentReport[]>("/urgent-reports?only_open=true")
      .then((rows) => setItems(Array.isArray(rows) ? rows : []))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить срочные сообщения"));
  }, []);

  useEffect(load, [load]);

  async function acknowledge(r: UrgentReport) {
    setBusy(true);
    try {
      await api.post(`/urgent-reports/${r.id}/acknowledge`, {});
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось принять сообщение");
    } finally {
      setBusy(false);
    }
  }

  if (items.length === 0 && !error) return null;
  return (
    <section className="change-review" aria-label="Срочные сообщения о студентах">
      {items.length > 0 && (
        <h3>
          Срочные сообщения <span className="tabbar__badge">{items.length}</span>
        </h3>
      )}
      {error && <div className="error-text">{error}</div>}
      <div className="change-review__list">
        {items.map((r) => (
          <div key={r.id} className="add-block">
            <p className="add-block__title">
              {URGENT_CATEGORIES[r.category]} · <Link to={`/students/${r.student_id}`}>{r.student_name}</Link> · {r.group_code}
            </p>
            <p className="hint">
              {r.author_name}, {formatDateRu(r.created_at.slice(0, 10))}
            </p>
            <p>{r.text}</p>
            <div className="actions">
              <button onClick={() => acknowledge(r)} disabled={busy}>
                Принято
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
