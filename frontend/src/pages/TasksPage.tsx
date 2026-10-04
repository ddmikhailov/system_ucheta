import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError, downloadFile } from "../api/client";
import TaskCreateForm from "../components/TaskCreateForm";
import { COLLECT_MODE_LABELS, REVIEWER_LABELS, TASK_STATUS_LABELS } from "../constants/tasks";
import { formatDateRu, formatServerDateTimeFull } from "../utils/date";
import type { ReviewQueueRow, TaskDetail, TaskListRow, TaskProgress } from "../api/types";

type Tab = "list" | "review" | "create";

function ProgressText({ p }: { p: TaskProgress }) {
  return (
    <span>
      сдано {p.submitted + p.accepted}/{p.total}, принято {p.accepted}
      {p.returned > 0 && <>, возвращено {p.returned}</>}
      {p.overdue > 0 && (
        <b style={{ marginLeft: 6 }}>просрочено {p.overdue}</b>
      )}
    </span>
  );
}

// Раздел «Задачи» для администрации, воспитательного отдела, зав. отделением и тьютора:
// список с прогрессом, очередь проверки, создание, карточка задачи с матрицей по группам.
export default function TasksPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const taskId = searchParams.get("task");
  const [tab, setTab] = useState<Tab>("list");
  const [list, setList] = useState<TaskListRow[] | null>(null);
  const [queue, setQueue] = useState<ReviewQueueRow[]>([]);
  const [error, setError] = useState<string | null>(null);

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
    return <TaskView id={taskId} onBack={() => { setSearchParams({}); loadList(); }} onDeleted={() => { setSearchParams({}); loadList(); }} />;
  }

  return (
    <div>
      <div className="tabs">
        <button className={tab === "list" ? "active" : ""} onClick={() => setTab("list")}>
          Задачи
        </button>
        <button className={tab === "review" ? "active" : ""} onClick={() => setTab("review")}>
          На проверке{queue.length > 0 ? ` (${queue.length})` : ""}
        </button>
        <button className={tab === "create" ? "active" : ""} onClick={() => setTab("create")}>
          + Новая задача
        </button>
      </div>
      {error && <div className="error-text">{error}</div>}

      {tab === "create" && (
        <TaskCreateForm
          onCreated={(task) => {
            loadList();
            setTab("list");
            setSearchParams({ task: String(task.id) });
          }}
        />
      )}

      {tab === "list" &&
        (list === null ? (
          <p className="hint">Загрузка…</p>
        ) : list.length === 0 ? (
          <p className="hint">Задач пока нет — создайте первую.</p>
        ) : (
          <table className="dash-table roster-table">
            <thead>
              <tr>
                <th>Задача</th>
                <th>Срок</th>
                <th>Прогресс</th>
                <th>Автор</th>
              </tr>
            </thead>
            <tbody>
              {list.map((t) => (
                <tr
                  key={t.id}
                  className="clickable-row"
                  onClick={() => setSearchParams({ task: String(t.id) })}
                  style={t.is_closed ? { opacity: 0.6 } : undefined}
                >
                  <td data-label="Задача">
                    {t.title} {t.is_closed && <span className="locked-badge">закрыта</span>}
                    <br />
                    <span className="hint">{COLLECT_MODE_LABELS[t.collect_mode]}</span>
                  </td>
                  <td data-label="Срок">{formatDateRu(t.due_date)}</td>
                  <td data-label="Прогресс">
                    <ProgressText p={t.progress} />
                  </td>
                  <td data-label="Автор">{t.author_name ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}

      {tab === "review" &&
        (queue.length === 0 ? (
          <p className="hint">Ничего не ждёт вашей проверки.</p>
        ) : (
          <table className="dash-table roster-table">
            <thead>
              <tr>
                <th>Задача</th>
                <th>Группа</th>
                <th>Отправлено</th>
                <th>Срок</th>
              </tr>
            </thead>
            <tbody>
              {queue.map((q) => (
                <tr key={q.id} className={q.is_overdue ? "not-submitted-row" : ""}>
                  <td data-label="Задача">
                    <Link to={`/tasks/assignment/${q.id}`} className="link-btn">
                      {q.title}
                    </Link>
                  </td>
                  <td data-label="Группа">
                    {q.group_code} <span className="hint">{q.department_name}</span>
                  </td>
                  <td data-label="Отправлено">{q.submitted_at ? formatServerDateTimeFull(q.submitted_at) : "—"}</td>
                  <td data-label="Срок">{formatDateRu(q.due_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
    </div>
  );
}

function TaskView({ id, onBack, onDeleted }: { id: string; onBack: () => void; onDeleted: () => void }) {
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");

  const load = useCallback(() => {
    api
      .get<TaskDetail>(`/tasks/${id}`)
      .then((t) => {
        setTask(t);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить задачу"));
  }, [id]);

  useEffect(load, [load]);

  if (!task) {
    return (
      <div>
        <button className="link-btn" onClick={onBack}>← К списку задач</button>
        {error ? <div className="error-text">{error}</div> : <p className="hint">Загрузка…</p>}
      </div>
    );
  }

  const act = async (action: () => Promise<unknown>, fail: string, after: () => void) => {
    setError(null);
    try {
      await action();
      after();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : fail);
    }
  };

  const shown = task.assignments.filter((a) => statusFilter === "all" || (statusFilter === "overdue" ? a.is_overdue : a.status === statusFilter));

  return (
    <div className="student-card">
      <p>
        <button className="link-btn" onClick={onBack}>← К списку задач</button>
      </p>
      <div className="student-card__header">
        <h2>{task.title}</h2>
        {task.is_closed && <span className="locked-badge">закрыта</span>}
      </div>
      <p className="hint">
        Срок {formatDateRu(task.due_date)} · {COLLECT_MODE_LABELS[task.collect_mode]} · проверяет: {REVIEWER_LABELS[task.reviewer_rule]} · автор:{" "}
        {task.author_name ?? "—"}
      </p>
      {task.description && <p style={{ whiteSpace: "pre-wrap" }}>{task.description}</p>}
      <p>
        <b>Поля формы:</b>{" "}
        {task.fields.map((f) => `${f.label}${f.required ? " *" : ""}`).join(", ")}
      </p>
      <p>
        <ProgressText p={task.progress} />
      </p>
      {error && <div className="error-text">{error}</div>}

      <p>
        <button
          className="link-btn"
          onClick={() => act(() => downloadFile(`/tasks/${task.id}/export`, `task_${task.id}.xlsx`), "Не удалось скачать файл", () => undefined)}
        >
          Выгрузить в Excel
        </button>
        {task.can_manage && (
          <>
            {" · "}
            <button
              className="link-btn"
              onClick={() => act(() => api.patch(`/tasks/${task.id}`, { is_closed: !task.is_closed }), "Не удалось изменить", load)}
            >
              {task.is_closed ? "Открыть снова" : "Закрыть задачу"}
            </button>
            {" · "}
            <button
              className="link-btn"
              onClick={() => {
                if (window.confirm(`Удалить задачу «${task.title}»?`))
                  act(() => api.delete(`/tasks/${task.id}`), "Не удалось удалить", onDeleted);
              }}
            >
              Удалить
            </button>
          </>
        )}
      </p>

      <div className="toolbar">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">Все статусы</option>
          <option value="overdue">Просроченные</option>
          {Object.entries(TASK_STATUS_LABELS).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </div>
      <table className="dash-table roster-table">
        <thead>
          <tr>
            <th>Группа</th>
            <th>Отделение</th>
            <th>Статус</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((a) => (
            <tr key={a.id} className={a.is_overdue ? "not-submitted-row" : ""}>
              <td data-label="Группа">
                <Link to={`/tasks/assignment/${a.id}`} className="link-btn">
                  {a.group_code}
                </Link>
              </td>
              <td data-label="Отделение">{a.department_name}</td>
              <td data-label="Статус">
                {TASK_STATUS_LABELS[a.status] ?? a.status} {a.is_overdue && <b>просрочено</b>}
              </td>
            </tr>
          ))}
          {shown.length === 0 && (
            <tr>
              <td colSpan={3}>Нет групп с таким статусом.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
