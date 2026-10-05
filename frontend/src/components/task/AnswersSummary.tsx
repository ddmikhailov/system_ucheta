import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { TaskSummary } from "../../api/types";
import { plural } from "../../utils/plural";

/** Сводка отправленных ответов: сколько выбрали каждый вариант, сколько «да»/«нет». Текстовые поля —
 * только число заполненных (сами ответы — в выгрузке). */
export default function AnswersSummary({ taskId, perStudent }: { taskId: number; perStudent: boolean }) {
  const [summary, setSummary] = useState<TaskSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<TaskSummary>(`/tasks/${taskId}/summary`)
      .then(setSummary)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить сводку"));
  }, [taskId]);

  if (error) return <div className="error-text">{error}</div>;
  if (!summary) return <p className="hint">Загрузка…</p>;
  if (summary.groups === 0) {
    return <p className="empty-state">Сводка появится, когда группы начнут отправлять ответы. Черновики сюда не попадают.</p>;
  }

  const unit: [string, string, string] = perStudent ? ["студенту", "студентам", "студентам"] : ["группе", "группам", "группам"];
  return (
    <div className="answers-summary">
      <p className="hint">
        По {summary.answers} {plural(summary.answers, unit)} из {summary.groups} {plural(summary.groups, ["группы", "групп", "групп"])}, отправивших
        ответ (на проверке и принятые).
      </p>
      {summary.fields.map((f) => {
        const max = Math.max(1, ...f.counts.map((c) => c.count));
        return (
          <section key={f.key} className="answers-summary__field" aria-label={f.label}>
            <h4>{f.label}</h4>
            {f.counts.length > 0 ? (
              <ul>
                {f.counts.map((c) => (
                  <li key={c.label}>
                    <span className="answers-summary__label">{c.label}</span>
                    <span className="meter answers-summary__meter" aria-hidden="true">
                      <i style={{ width: `${(c.count / max) * 100}%` }} />
                    </span>
                    <b>{c.count}</b>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="hint">
                Заполнено: {f.filled} из {summary.answers}. Сами ответы — в выгрузке Excel.
              </p>
            )}
          </section>
        );
      })}
    </div>
  );
}
