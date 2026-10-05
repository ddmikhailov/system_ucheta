import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, downloadFile } from "../../api/client";
import { COLLECT_MODE_LABELS, REVIEWER_LABELS, TASK_STATUS_LABELS } from "../../constants/tasks";
import { formatDateRu, formatDueShort, formatServerDateTimeFull } from "../../utils/date";
import { relativeDue } from "../../utils/deadline";
import { dialogs, toast } from "../../utils/feedback";
import { plural } from "../../utils/plural";
import { markKind } from "../../utils/statusMark";
import type { RemindResult, TaskDetail } from "../../api/types";
import StatusMark from "../StatusMark";
import AnswersSummary from "./AnswersSummary";
import GroupMap from "./GroupMap";
import ProgressStrip from "./ProgressStrip";

type View = "map" | "answers" | "table";

const GROUPS: [string, string, string] = ["группе", "группам", "группам"];

// Что видно в таблице о ходе проверки: кто принял и когда, либо когда отправлено на проверку.
function reviewSummary(a: TaskDetail["assignments"][number]): string {
  if (a.reviewed_at && (a.status === "accepted" || a.status === "returned")) {
    const who = a.reviewed_by_name ?? "без проверки";
    return `${a.status === "accepted" ? "Принято" : "Возвращено"} ${formatServerDateTimeFull(a.reviewed_at)}, ${who}`;
  }
  if (a.submitted_at && a.status === "submitted") return `Отправлено ${formatServerDateTimeFull(a.submitted_at)}`;
  return "—";
}

/** Меню второстепенных действий: одна главная кнопка на экране, остальное — здесь. */
function MoreMenu({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    function close(e: MouseEvent) {
      if (ref.current?.open && !ref.current.contains(e.target as Node)) ref.current.open = false;
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && ref.current?.open) {
        ref.current.open = false;
        ref.current.querySelector("summary")?.focus();
      }
    }
    document.addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", close);
      document.removeEventListener("keydown", onKey);
    };
  }, []);
  return (
    <details className="more-menu" ref={ref}>
      <summary>Ещё</summary>
      <div className="more-menu__panel" onClick={() => ref.current && (ref.current.open = false)}>
        {children}
      </div>
    </details>
  );
}

// Карточка задачи у администрации, воспитательного отдела, зав. отделением и тьютора.
export default function TaskView({
  id,
  onBack,
  onDeleted,
  onAddStep,
}: {
  id: string;
  onBack: () => void;
  onDeleted: () => void;
  onAddStep: (task: TaskDetail) => void;
}) {
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("map");
  const [statusFilter, setStatusFilter] = useState("all");
  const [busy, setBusy] = useState(false);

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
        <button className="link-btn" onClick={onBack}>
          ← К списку задач
        </button>
        {error ? <div className="error-text">{error}</div> : <p className="hint">Загрузка…</p>}
      </div>
    );
  }

  const act = async (action: () => Promise<unknown>, fail: string, after: () => void) => {
    setError(null);
    setBusy(true);
    try {
      await action();
      after();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : fail;
      setError(message);
      toast(message, "error");
    } finally {
      setBusy(false);
    }
  };

  const lagging = task.assignments.filter((a) => !a.is_locked && ["new", "in_progress", "returned"].includes(a.status));
  const isLastStep = task.steps.length === 0 || task.steps[task.steps.length - 1].id === task.id;
  const shown = task.assignments.filter(
    (a) => statusFilter === "all" || (statusFilter === "overdue" ? a.is_overdue : a.status === statusFilter)
  );

  async function remind() {
    if (!task) return;
    const ok = await dialogs.confirm(
      `Напомнить кураторам ${lagging.length} ${plural(lagging.length, ["группы", "групп", "групп"])}, которые ещё не отправили ответ? Напоминание придёт в колокольчик.`,
      { confirmLabel: "Напомнить" }
    );
    if (!ok) return;
    await act(
      () =>
        api.post<RemindResult>(`/tasks/${task.id}/remind`).then((r) => {
          if (r.sent > 0) {
            toast(
              `Напоминание отправлено ${r.sent} ${plural(r.sent, GROUPS)}` +
                (r.skipped > 0 ? `; ${r.skipped} пропущено: уже напоминали сегодня или нет куратора` : "")
            );
          } else {
            toast("Сегодня всем уже напоминали, или у групп нет куратора", "info");
          }
        }),
      "Не удалось отправить напоминание",
      () => undefined
    );
  }

  async function saveTemplate() {
    if (!task) return;
    const name = await dialogs.prompt("Название шаблона", task.title, { confirmLabel: "Сохранить шаблон" });
    if (name === null) return;
    await act(
      () => api.post("/tasks/templates", { task_id: task.id, name }),
      "Не удалось сохранить шаблон",
      () => toast(`Шаблон «${name.trim() || task.title}» сохранён — он доступен при создании новой задачи`)
    );
  }

  async function remove() {
    if (!task) return;
    if (!(await dialogs.confirm(`Удалить задачу «${task.title}»?`, { confirmLabel: "Удалить", danger: true }))) return;
    await act(() => api.delete(`/tasks/${task.id}`), "Не удалось удалить", () => {
      toast("Задача удалена");
      onDeleted();
    });
  }

  return (
    <div className="task-view">
      <p>
        <button className="link-btn" onClick={onBack}>
          ← К списку задач
        </button>
      </p>
      <header className="task-view__head">
        <div className="task-view__title">
          <div className="assignment__meta">
            <span>
              срок {formatDueShort(task.due_date)}
              {task.is_closed ? `, ${formatDateRu(task.due_date)}` : `, ${relativeDue(task.due_date)}`}
            </span>
            {task.is_closed && <span className="locked-badge">закрыта</span>}
          </div>
          <h2>{task.title}</h2>
          <div className="assignment__meta">
            <span>{COLLECT_MODE_LABELS[task.collect_mode]}</span>
            <span>проверяет: {REVIEWER_LABELS[task.reviewer_rule]}</span>
            <span>автор: {task.author_name ?? "—"}</span>
          </div>
        </div>
        <div className="task-view__actions">
          {!task.is_closed && lagging.length > 0 && (
            <button className="btn-primary" onClick={remind} disabled={busy}>
              Напомнить {lagging.length} {plural(lagging.length, GROUPS)}
            </button>
          )}
          <button
            className="btn-secondary"
            onClick={() => act(() => downloadFile(`/tasks/${task.id}/export`, `task_${task.id}.xlsx`), "Не удалось скачать файл", () => undefined)}
          >
            Выгрузить в Excel
          </button>
          <MoreMenu>
            <button onClick={saveTemplate}>Сохранить как шаблон</button>
            {task.can_manage && isLastStep && <button onClick={() => onAddStep(task)}>Добавить следующий шаг</button>}
            {task.can_manage && (
              <button
                onClick={() =>
                  act(() => api.patch(`/tasks/${task.id}`, { is_closed: !task.is_closed }), "Не удалось изменить", () => {
                    toast(task.is_closed ? "Задача снова открыта" : "Задача закрыта: править ответы больше нельзя");
                    load();
                  })
                }
              >
                {task.is_closed ? "Открыть снова" : "Закрыть задачу"}
              </button>
            )}
            {task.can_manage && (
              <button className="danger-link" onClick={remove}>
                Удалить
              </button>
            )}
          </MoreMenu>
        </div>
      </header>

      {task.steps.length > 1 && (
        <ol className="steps-chain" aria-label="Шаги задачи">
          {task.steps.map((s) => (
            <li key={s.id} className={s.id === task.id ? "is-current" : ""}>
              {s.id === task.id ? (
                <b>
                  {s.step_no}. {s.title}
                </b>
              ) : (
                <Link to={`?task=${s.id}`} className="link-btn">
                  {s.step_no}. {s.title}
                </Link>
              )}
              <span className="hint">до {formatDateRu(s.due_date)}</span>
            </li>
          ))}
        </ol>
      )}
      {task.unlock_on && (
        <p className="hint">Этот шаг открывается {task.unlock_on === "submitted" ? "после сдачи" : "после приёмки"} предыдущего.</p>
      )}
      {task.description && <p className="assignment__description">{task.description}</p>}
      <p className="task-view__fields">
        <span className="hint">Форма ответа:</span>{" "}
        {task.fields.map((f) => (
          <span key={f.key ?? f.label} className="field-chip">
            {f.label}
            {f.required && <span className="required-mark"> обяз.</span>}
          </span>
        ))}
      </p>

      <ProgressStrip p={task.progress} />
      {error && (
        <div className="error-text" role="alert">
          {error}
        </div>
      )}

      <div className="segmented task-view__tabs" role="group" aria-label="Как показать группы">
        {(
          [
            ["map", "Карта групп"],
            ["answers", "Ответы"],
            ["table", "Таблица"],
          ] as [View, string][]
        ).map(([key, label]) => (
          <button key={key} aria-pressed={view === key} className={view === key ? "active" : ""} onClick={() => setView(key)}>
            {label}
          </button>
        ))}
      </div>

      {view === "map" &&
        (task.assignments.length === 0 ? (
          <p className="empty-state">Групп в вашем охвате нет.</p>
        ) : (
          <GroupMap assignments={task.assignments} />
        ))}

      {view === "answers" && <AnswersSummary taskId={task.id} perStudent={task.collect_mode !== "group"} />}

      {view === "table" && (
        <>
          <div className="toolbar">
            <label className="filter-check" htmlFor="task-status-filter">
              Статус
            </label>
            <select id="task-status-filter" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
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
                <th>Проверка</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((a) => (
                <tr key={a.id}>
                  <td data-label="Группа">
                    <Link to={`/tasks/assignment/${a.id}`} className="link-btn">
                      {a.group_code}
                    </Link>
                  </td>
                  <td data-label="Отделение">{a.department_name}</td>
                  <td data-label="Статус">
                    <StatusMark
                      kind={markKind(a)}
                      withLabel
                      label={(TASK_STATUS_LABELS[a.status] ?? a.status) + (a.is_overdue && a.status !== "accepted" ? ", просрочено" : "")}
                    />
                  </td>
                  <td data-label="Проверка">{reviewSummary(a)}</td>
                </tr>
              ))}
              {shown.length === 0 && (
                <tr>
                  <td colSpan={4}>Нет групп с таким статусом.</td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
