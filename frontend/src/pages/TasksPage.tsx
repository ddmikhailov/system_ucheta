import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import TaskCreateForm from "../components/TaskCreateForm";
import type { AfterTask } from "../components/TaskCreateForm";
import TaskTemplatesTab from "../components/TaskTemplatesTab";
import ProgressStrip from "../components/task/ProgressStrip";
import ReviewMode from "../components/task/ReviewMode";
import TaskView from "../components/task/TaskView";
import { COLLECT_MODE_LABELS } from "../constants/tasks";
import { formatDateRu, formatDueShort, todayIso } from "../utils/date";
import { daysUntil, relativeDue } from "../utils/deadline";
import type { ReviewQueueRow, TaskListRow } from "../api/types";

type Tab = "list" | "review" | "templates" | "create";
type Filter = "active" | "mine" | "overdue" | "closed";

const FILTERS: [Filter, string][] = [
  ["active", "Активные"],
  ["mine", "Мои"],
  ["overdue", "С просрочкой"],
  ["closed", "Закрытые"],
];

function matches(t: TaskListRow, filter: Filter, userId: number | undefined): boolean {
  if (filter === "closed") return t.is_closed;
  if (t.is_closed) return false;
  if (filter === "mine") return t.author_id === userId;
  if (filter === "overdue") return t.progress.overdue > 0;
  return true;
}

// Раздел «Задачи» для администрации, воспитательного отдела, зав. отделением и тьютора:
// список с прогрессом, режим проверки, шаблоны, создание, карточка задачи с картой групп.
export default function TasksPage() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const taskId = searchParams.get("task");
  const [tab, setTab] = useState<Tab>("list");
  const [filter, setFilter] = useState<Filter>("active");
  const [list, setList] = useState<TaskListRow[] | null>(null);
  const [queue, setQueue] = useState<ReviewQueueRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [afterTask, setAfterTask] = useState<AfterTask | null>(null);

  const loadList = useCallback(() => {
    api
      .get<TaskListRow[]>("/tasks")
      .then((rows) => {
        setList(rows);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить задачи"));
    api.get<ReviewQueueRow[]>("/tasks/review-queue").then(setQueue).catch(() => setQueue([]));
  }, []);

  useEffect(loadList, [loadList]);

  if (taskId) {
    return (
      <TaskView
        id={taskId}
        onBack={() => {
          setSearchParams({});
          loadList();
        }}
        onDeleted={() => {
          setSearchParams({});
          loadList();
        }}
        onAddStep={(t) => {
          setAfterTask({ id: t.id, title: t.title, due_date: t.due_date });
          setTab("create");
          setSearchParams({});
        }}
      />
    );
  }

  const today = todayIso();
  const counts = Object.fromEntries(FILTERS.map(([f]) => [f, list?.filter((t) => matches(t, f, user?.id)).length ?? 0]));
  const shown = (list ?? [])
    .filter((t) => matches(t, filter, user?.id))
    .sort((a, b) => (filter === "closed" ? b.due_date.localeCompare(a.due_date) : a.due_date.localeCompare(b.due_date)));

  const tabs: [Tab, string][] = [
    ["list", "Задачи"],
    ["review", queue.length > 0 ? `На проверке ${queue.length}` : "На проверке"],
    ["templates", "Шаблоны"],
  ];

  return (
    <div className="tasks-page">
      <div className="page-head">
        <h2>Задачи</h2>
        <button
          className={tab === "create" ? "btn-secondary" : "btn-primary"}
          onClick={() => {
            setAfterTask(null);
            setTab("create");
          }}
        >
          + Новая задача
        </button>
      </div>
      <div className="tabs" role="group" aria-label="Разделы задач">
        {tabs.map(([key, label]) => (
          <button key={key} aria-pressed={tab === key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>
      {error && <div className="error-text">{error}</div>}

      {tab === "templates" && <TaskTemplatesTab />}

      {tab === "create" && (
        <TaskCreateForm
          key={afterTask ? `after-${afterTask.id}` : "new"}
          afterTask={afterTask}
          onCreated={(task) => {
            setAfterTask(null);
            loadList();
            setTab("list");
            setSearchParams({ task: String(task.id) });
          }}
        />
      )}

      {tab === "review" && (
        <ReviewMode
          queue={queue}
          onDecided={(id) => {
            setQueue((q) => q.filter((x) => x.id !== id));
            api.get<TaskListRow[]>("/tasks").then(setList).catch(() => undefined);
          }}
        />
      )}

      {tab === "list" && (
        <>
          <div className="filter-chips" role="group" aria-label="Какие задачи показать">
            {FILTERS.map(([key, label]) => (
              <button key={key} className={`chip${filter === key ? " active" : ""}`} aria-pressed={filter === key} onClick={() => setFilter(key)}>
                {label} {counts[key]}
              </button>
            ))}
          </div>
          {list === null ? (
            error ? null : <p className="hint">Загрузка…</p>
          ) : list.length === 0 ? (
            <p className="empty-state">Задач пока нет. Создайте первую: «+ Новая задача» вверху справа.</p>
          ) : shown.length === 0 ? (
            <p className="empty-state">В этом списке пусто.</p>
          ) : (
            <ul className="task-list">
              {shown.map((t) => {
                const days = daysUntil(t.due_date, today);
                const hot = !t.is_closed && days < 0 && t.progress.accepted < t.progress.total;
                return (
                  <li key={t.id} className={`task-list__item${t.is_closed ? " is-closed" : ""}`}>
                    <div className="task-list__main">
                      <button className="task-list__title" onClick={() => setSearchParams({ task: String(t.id) })}>
                        {t.title}
                      </button>
                      <div className="inbox-row__meta">
                        {t.step_total ? <span>шаг {t.step_no} из {t.step_total}</span> : null}
                        <span>{COLLECT_MODE_LABELS[t.collect_mode]}</span>
                        <span>автор: {t.author_name ?? "—"}</span>
                        {t.is_closed && <span className="locked-badge">закрыта</span>}
                      </div>
                    </div>
                    <ProgressStrip p={t.progress} />
                    <div className={`inbox-row__due${hot ? " is-hot" : !t.is_closed && days <= 2 ? " is-warn" : ""}`}>
                      <b>{t.is_closed || (days < 0 && !hot) ? formatDateRu(t.due_date) : relativeDue(t.due_date, today)}</b>
                      <span>{formatDueShort(t.due_date)}</span>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
