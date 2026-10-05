import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import StatusMark from "../components/StatusMark";
import { markKind } from "../utils/statusMark";
import { COLLECT_MODE_LABELS } from "../constants/tasks";
import { daysUntil, relativeDue } from "../utils/deadline";
import { formatDueShort, todayIso } from "../utils/date";
import { plural } from "../utils/plural";
import type { MyAssignmentRow } from "../api/types";

type Horizon = "hot" | "week" | "later" | "review";

const HORIZONS: { key: Horizon; title: string; empty?: string }[] = [
  { key: "hot", title: "Горит" },
  { key: "week", title: "На этой неделе" },
  { key: "later", title: "Позже" },
  { key: "review", title: "Ждёт проверки" },
];

// После «из N» — родительный падеж: «из 1 студента», «из 25 студентов».
const STUDENTS: [string, string, string] = ["студента", "студентов", "студентов"];
const FIELDS: [string, string, string] = ["поля", "полей", "полей"];

/** В какой горизонт попадает открытая задача: возврат, просрочка и срок «сегодня» — горят. */
function horizonOf(r: MyAssignmentRow, today: string): Horizon {
  if (r.status === "submitted") return "review";
  if (r.is_locked) return "later";
  const days = daysUntil(r.due_date, today);
  if (r.status === "returned" || r.is_overdue || days <= 0) return "hot";
  return days <= 7 ? "week" : "later";
}

function progressText(r: MyAssignmentRow): string {
  if (r.total === 0) return r.collect_mode === "selected" ? "никто не отмечен" : "—";
  if (r.filled === 0) return "не начато";
  const unit = r.collect_mode === "group" ? FIELDS : STUDENTS;
  return `${r.filled} из ${r.total} ${plural(r.total, unit)}`;
}

function TaskRow({ r, today }: { r: MyAssignmentRow; today: string }) {
  const kind = markKind(r);
  const days = daysUntil(r.due_date, today);
  const dueClass = r.status === "accepted" ? "" : r.is_overdue || days <= 0 ? " is-hot" : days <= 2 ? " is-warn" : "";
  const percent = r.total > 0 ? Math.round((r.filled / r.total) * 100) : 0;
  return (
    <li className={`inbox-row${r.is_locked ? " is-locked" : ""}`}>
      <StatusMark kind={kind} />
      <div className="inbox-row__main">
        {r.is_locked ? (
          <span className="inbox-row__title">{r.title}</span>
        ) : (
          <Link to={`/tasks/assignment/${r.id}`} className="inbox-row__title">
            {r.title}
          </Link>
        )}
        <div className="inbox-row__meta">
          <span className="group-chip">{r.group_code}</span>
          <span>{COLLECT_MODE_LABELS[r.collect_mode]}</span>
          {r.step_total ? <span>шаг {r.step_no} из {r.step_total}</span> : null}
          {r.is_locked && <span>откроется после предыдущего шага</span>}
          {r.is_closed && r.status !== "accepted" && <span>задача закрыта</span>}
        </div>
        {r.review_comment && <div className="inbox-row__note">Вернули: «{r.review_comment}»</div>}
      </div>
      {!r.is_locked && (
        <div className="inbox-row__progress">
          <div className="meter" aria-hidden="true">
            <i style={{ width: `${percent}%` }} />
          </div>
          <span>{progressText(r)}</span>
        </div>
      )}
      <div className={`inbox-row__due${dueClass}`}>
        <b>{r.status === "accepted" ? "принято" : relativeDue(r.due_date, today)}</b>
        <span>{formatDueShort(r.due_date, today)}</span>
      </div>
    </li>
  );
}

// «Мои задачи» куратора: входящие по срочности. Сначала то, что горит, сданное ждёт проверки
// отдельно, принятые и закрытые — во второй вкладке.
export default function MyTasksPage() {
  const [rows, setRows] = useState<MyAssignmentRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"active" | "done">("active");

  useEffect(() => {
    api
      .get<MyAssignmentRow[]>("/tasks/my")
      .then(setRows)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить задачи"));
  }, []);

  if (error) return <div className="error-text">{error}</div>;
  if (!rows) return <p className="hint">Загрузка…</p>;

  const today = todayIso();
  const isDone = (r: MyAssignmentRow) => r.status === "accepted" || (r.is_closed && r.status !== "submitted");
  const active = rows.filter((r) => !isDone(r));
  const done = rows.filter(isDone).sort((a, b) => b.due_date.localeCompare(a.due_date));
  const byHorizon = new Map<Horizon, MyAssignmentRow[]>();
  for (const r of active) {
    const h = horizonOf(r, today);
    byHorizon.set(h, [...(byHorizon.get(h) ?? []), r]);
  }
  for (const list of byHorizon.values()) {
    list.sort((a, b) => Number(a.is_locked) - Number(b.is_locked) || a.due_date.localeCompare(b.due_date));
  }

  return (
    <div className="inbox">
      <div className="page-head">
        <h2>Мои задачи</h2>
        <div className="segmented" role="group" aria-label="Какие задачи показать">
          <button aria-pressed={view === "active"} className={view === "active" ? "active" : ""} onClick={() => setView("active")}>
            Активные {active.length}
          </button>
          <button aria-pressed={view === "done"} className={view === "done" ? "active" : ""} onClick={() => setView("done")}>
            Готово {done.length}
          </button>
        </div>
      </div>

      {view === "active" &&
        (active.length === 0 ? (
          <p className="empty-state">Активных задач нет. Новые появятся здесь, а о сроках напомнит колокольчик.</p>
        ) : (
          HORIZONS.filter((h) => byHorizon.has(h.key)).map((h) => {
            const list = byHorizon.get(h.key)!;
            return (
              <section key={h.key} className={`inbox-section inbox-section--${h.key}`} aria-label={h.title}>
                <h3>
                  {h.title} <span className="inbox-section__count">{list.length}</span>
                </h3>
                <ul className="inbox-list">
                  {list.map((r) => (
                    <TaskRow key={r.id} r={r} today={today} />
                  ))}
                </ul>
              </section>
            );
          })
        ))}

      {view === "done" &&
        (done.length === 0 ? (
          <p className="empty-state">Принятых задач пока нет.</p>
        ) : (
          <ul className="inbox-list">
            {done.map((r) => (
              <TaskRow key={r.id} r={r} today={today} />
            ))}
          </ul>
        ))}
    </div>
  );
}
