import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import { formatDateRu, formatServerDateTime } from "../../utils/date";
import { toast } from "../../utils/feedback";
import { valueText } from "../../utils/taskAnswers";
import type { AssignmentDetail, ReviewQueueRow } from "../../api/types";

/** Режим проверки: очередь слева, ответ группы справа, «Принять» и «Вернуть» — сверху, без перехода на
 * отдельную страницу. После решения открывается следующий ответ. */
export default function ReviewMode({ queue, onDecided }: { queue: ReviewQueueRow[]; onDecided: (id: number) => void }) {
  const [currentId, setCurrentId] = useState<number | null>(queue[0]?.id ?? null);
  const [loaded, setLoaded] = useState<AssignmentDetail | null>(null);
  const [loadError, setLoadError] = useState<{ id: number; message: string } | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const commentRef = useRef<HTMLTextAreaElement>(null);

  // Текущий ответ ушёл из очереди (решение принято) — берём следующий.
  const current = queue.find((q) => q.id === currentId) ?? queue[0] ?? null;

  const currentKey = current?.id ?? null;
  // Показываем только ответ текущей группы: пока грузится следующий, прежний не мелькает.
  const detail = loaded && loaded.id === currentKey ? loaded : null;
  const loadMessage = loadError && loadError.id === currentKey ? loadError.message : null;
  useEffect(() => {
    if (currentKey === null) return;
    let cancelled = false;
    api
      .get<AssignmentDetail>(`/tasks/assignments/${currentKey}`)
      .then((d) => !cancelled && setLoaded(d))
      .catch(
        (err) =>
          !cancelled && setLoadError({ id: currentKey, message: err instanceof ApiError ? err.message : "Не удалось загрузить ответ" })
      );
    return () => {
      cancelled = true;
    };
  }, [currentKey]);

  const decide = useCallback(
    async (action: "accept" | "return") => {
      if (!current || busy) return;
      if (action === "return" && !comment.trim()) {
        setError("Напишите, что исправить: без комментария вернуть нельзя");
        commentRef.current?.focus();
        return;
      }
      setBusy(true);
      setError(null);
      try {
        const index = queue.findIndex((q) => q.id === current.id);
        await api.post(`/tasks/assignments/${current.id}/review`, { action, comment: comment.trim() || null });
        toast(`${current.group_code}: ${action === "accept" ? "принято" : "возвращено на доработку"}`);
        setComment("");
        setCurrentId(queue[index + 1]?.id ?? queue[index - 1]?.id ?? null);
        onDecided(current.id);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Не удалось сохранить решение");
      } finally {
        setBusy(false);
      }
    },
    [busy, comment, current, onDecided, queue]
  );

  if (queue.length === 0) return <p className="empty-state">Ничего не ждёт вашей проверки.</p>;

  const perStudent = detail?.collect_mode !== "group";
  const rows = detail ? detail.rows.filter((r) => detail.collect_mode !== "selected" || r.is_included) : [];

  return (
    <div className="review-mode">
      <ol className="review-mode__queue" aria-label="Очередь проверки">
        {queue.map((q) => (
          <li key={q.id}>
            <button
              type="button"
              className={q.id === current?.id ? "is-current" : ""}
              aria-current={q.id === current?.id ? "true" : undefined}
              onClick={() => {
                setCurrentId(q.id);
                setComment("");
                setError(null);
              }}
            >
              <b>{q.group_code}</b>
              <span>{q.title}</span>
              <small>
                {q.department_name}
                {q.submitted_at ? `, отправлено ${formatServerDateTime(q.submitted_at)}` : ""}
                {q.is_overdue ? ", после срока" : ""}
              </small>
            </button>
          </li>
        ))}
      </ol>

      <section className="review-mode__pane" aria-label="Ответ группы">
        {current && (
          <>
            <div className="review-mode__head">
              <div>
                <h3>
                  {current.group_code}: {current.title}
                </h3>
                <div className="assignment__meta">
                  <span>срок {formatDateRu(current.due_date)}</span>
                  {detail && detail.review_steps > 1 && (
                    <span>
                      ступень {detail.review_step} из {detail.review_steps}
                    </span>
                  )}
                  <Link to={`/tasks/assignment/${current.id}`} className="link-btn">
                    Открыть целиком
                  </Link>
                </div>
              </div>
            </div>
            <div className="review-mode__decide">
              <label className="form-field" htmlFor="review-mode-comment">
                Комментарий проверяющего
              </label>
              <textarea
                id="review-mode-comment"
                ref={commentRef}
                rows={2}
                placeholder="Что исправить (обязательно, если возвращаете)"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
              <div className="review-panel__actions">
                <button className="btn-primary" onClick={() => decide("accept")} disabled={busy || !detail}>
                  Принять
                </button>
                <button className="danger-btn" onClick={() => decide("return")} disabled={busy || !detail}>
                  Вернуть
                </button>
              </div>
            </div>
            {(error || loadMessage) && (
              <div className="error-text" role="alert">
                {error ?? loadMessage}
              </div>
            )}
            {!detail && !loadMessage && <p className="hint">Загрузка…</p>}
            {detail && !perStudent && (
              <dl className="review-mode__group">
                {detail.fields.map((f) => (
                  <div key={f.key}>
                    <dt>{f.label}</dt>
                    <dd>
                      {f.type === "link" && typeof detail.group_values[f.key] === "string" ? (
                        <a href={String(detail.group_values[f.key])} target="_blank" rel="noreferrer noopener">
                          {String(detail.group_values[f.key])}
                        </a>
                      ) : (
                        valueText(f, detail.group_values[f.key])
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
            {detail && perStudent && (
              <div className="table-scroll">
                <table className="dash-table roster-table review-mode__table">
                  <thead>
                    <tr>
                      <th>Студент</th>
                      {detail.fields.map((f) => (
                        <th key={f.key}>{f.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.student_id}>
                        <td data-label="Студент">{r.student_name}</td>
                        {detail.fields.map((f) => (
                          <td key={f.key} data-label={f.label}>
                            {valueText(f, r.values[f.key])}
                          </td>
                        ))}
                      </tr>
                    ))}
                    {rows.length === 0 && (
                      <tr>
                        <td colSpan={detail.fields.length + 1}>Куратор отметил, что задача никого в группе не касается.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
            {detail && detail.comments.length > 0 && (
              <p className="hint">Комментариев к ответу: {detail.comments.length} — они на странице ответа целиком.</p>
            )}
          </>
        )}
      </section>
    </div>
  );
}
