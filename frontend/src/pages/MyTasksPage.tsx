import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { COLLECT_MODE_LABELS, TASK_STATUS_LABELS } from "../constants/tasks";
import { formatDateRu } from "../utils/date";
import type { MyAssignmentRow } from "../api/types";

const ORDER = ["returned", "in_progress", "new", "submitted", "accepted"];

// «Мои задачи» куратора: что нужно сдать, с дедлайнами; сначала то, что требует действий.
export default function MyTasksPage() {
  const [rows, setRows] = useState<MyAssignmentRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showDone, setShowDone] = useState(false);

  useEffect(() => {
    api
      .get<MyAssignmentRow[]>("/tasks/my")
      .then(setRows)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить задачи"));
  }, []);

  if (error) return <div className="error-text">{error}</div>;
  if (!rows) return <p className="hint">Загрузка…</p>;

  const open = rows.filter((r) => r.status !== "accepted");
  const done = rows.filter((r) => r.status === "accepted");
  const sorted = [...open].sort(
    (a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status) || a.due_date.localeCompare(b.due_date)
  );

  const table = (list: MyAssignmentRow[]) => (
    <table className="dash-table roster-table">
      <thead>
        <tr>
          <th>Задача</th>
          <th>Группа</th>
          <th>Срок</th>
          <th>Статус</th>
        </tr>
      </thead>
      <tbody>
        {list.map((r) => (
          <tr key={r.id} className={r.is_overdue ? "not-submitted-row" : ""}>
            <td data-label="Задача">
              <Link to={`/tasks/assignment/${r.id}`} className="link-btn">
                {r.title}
              </Link>
              <br />
              <span className="hint">{COLLECT_MODE_LABELS[r.collect_mode]}</span>
            </td>
            <td data-label="Группа">{r.group_code}</td>
            <td data-label="Срок">
              {formatDateRu(r.due_date)} {r.is_overdue && <b>просрочено</b>}
            </td>
            <td data-label="Статус">{TASK_STATUS_LABELS[r.status] ?? r.status}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  return (
    <div>
      <h2>Мои задачи</h2>
      {sorted.length === 0 ? <p className="hint">Активных задач нет.</p> : table(sorted)}
      {done.length > 0 && (
        <>
          <p>
            <button className="link-btn" onClick={() => setShowDone((v) => !v)}>
              {showDone ? "Скрыть принятые" : `Принятые (${done.length})`}
            </button>
          </p>
          {showDone && table(done)}
        </>
      )}
    </div>
  );
}
