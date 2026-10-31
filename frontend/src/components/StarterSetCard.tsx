import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import { formatDateRu, todayIso } from "../utils/date";
import { dialogs, toast } from "../utils/feedback";
import type { StarterTask } from "../api/types";

// Готовый набор «Адаптация первого курса» (п. 3.1.5 Положения о кураторе): шесть задач по неделям всем группам 1 курса.
export default function StarterSetCard({ onLaunched }: { onLaunched?: () => void }) {
  const [start, setStart] = useState(todayIso());
  const [tasks, setTasks] = useState<StarterTask[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!start) return;
    api
      .get<StarterTask[]>(`/tasks/starter-sets/first-year?start_date=${start}`)
      .then(setTasks)
      .catch(() => setTasks([]));
  }, [start]);

  async function launch() {
    if (!(await dialogs.confirm("Поставить шесть задач «Адаптация первого курса» всем группам 1 курса, которые вы видите?", { confirmLabel: "Поставить" }))) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/tasks/starter-sets/first-year", { start_date: start });
      toast("Набор задач поставлен");
      onLaunched?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось поставить набор");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="starter-set">
      <h3>Набор «Адаптация первого курса»</h3>
      <p className="hint">Шесть задач по неделям для кураторов групп 1 курса: знакомство, беседы, досье, «Мой ID», собрание, итог.</p>
      <label>
        Дата начала
        <input type="date" value={start} min={todayIso()} onChange={(e) => setStart(e.target.value)} />
      </label>
      {tasks.length > 0 && (
        <ol className="starter-set__list">
          {tasks.map((t) => (
            <li key={t.week}>
              {t.title} — срок {formatDateRu(t.due_date)}
            </li>
          ))}
        </ol>
      )}
      {error && <div className="error-text">{error}</div>}
      <button onClick={launch} disabled={busy || !start}>
        Поставить задачи
      </button>
    </section>
  );
}
