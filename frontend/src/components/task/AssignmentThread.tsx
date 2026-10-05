import { useState } from "react";
import type { FormEvent } from "react";
import { HISTORY_LABELS } from "../../constants/tasks";
import { formatServerDateTimeFull, parseServerDateTime } from "../../utils/date";
import type { TaskCommentRead, TaskHistoryEvent } from "../../api/types";

type Item =
  | { kind: "event"; at: string; event: TaskHistoryEvent }
  | { kind: "comment"; at: string; comment: TaskCommentRead };

/** Обсуждение назначения: ход проверки и комментарии одной лентой по времени — раньше это были два
 * отдельных списка внизу страницы, и замечание проверяющего терялось среди событий. */
export default function AssignmentThread({
  history,
  comments,
  reviewSteps,
  studentNames,
  students,
  busy,
  onComment,
}: {
  history: TaskHistoryEvent[];
  comments: TaskCommentRead[];
  reviewSteps: number;
  studentNames: Map<number, string>;
  /** Кого можно выбрать адресатом комментария; пусто — комментарий только ко всему ответу. */
  students: { id: number; name: string }[];
  busy: boolean;
  onComment: (text: string, studentId: number | null) => Promise<boolean>;
}) {
  const [text, setText] = useState("");
  const [studentId, setStudentId] = useState("");

  const items: Item[] = [
    ...history.map((e) => ({ kind: "event" as const, at: e.at, event: e })),
    ...comments.map((c) => ({ kind: "comment" as const, at: c.created_at, comment: c })),
  ].sort((a, b) => parseServerDateTime(a.at).getTime() - parseServerDateTime(b.at).getTime());

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    if (await onComment(text, studentId ? Number(studentId) : null)) {
      setText("");
      setStudentId("");
    }
  }

  return (
    <section className="thread" aria-label="Обсуждение">
      <h3>Обсуждение</h3>
      {items.length === 0 ? (
        <p className="hint">Пока пусто. Здесь появятся отправка, решения проверяющего и комментарии.</p>
      ) : (
        <ol className="thread__list">
          {items.map((item) =>
            item.kind === "event" ? (
              <li key={`e-${item.at}-${item.event.kind}`} className={`thread__event thread__event--${item.event.kind}`}>
                <span className="thread__dot" aria-hidden="true" />
                <div>
                  <b>{HISTORY_LABELS[item.event.kind] ?? item.event.kind}</b>
                  {item.event.step != null && reviewSteps > 1 && ` (ступень ${item.event.step} из ${reviewSteps})`}
                  <div className="thread__meta">
                    {formatServerDateTimeFull(item.at)}
                    {item.event.user_name && `, ${item.event.user_name}`}
                  </div>
                </div>
              </li>
            ) : (
              <li key={`c-${item.comment.id}`} className="thread__comment">
                <span className="thread__dot" aria-hidden="true" />
                <div>
                  <div className="thread__meta">
                    <b>{item.comment.author_name ?? "—"}</b>, {formatServerDateTimeFull(item.at)}
                    {item.comment.student_id != null && (
                      <span className="group-chip">{studentNames.get(item.comment.student_id) ?? "студент"}</span>
                    )}
                  </div>
                  <p className="thread__text">{item.comment.text}</p>
                </div>
              </li>
            )
          )}
        </ol>
      )}
      <form className="thread__form" onSubmit={submit}>
        {students.length > 0 && (
          <label className="form-field">
            К кому комментарий
            <select value={studentId} onChange={(e) => setStudentId(e.target.value)}>
              <option value="">Ко всему ответу</option>
              {students.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="form-field thread__field">
          Комментарий
          <input placeholder="Что уточнить или поправить" value={text} onChange={(e) => setText(e.target.value)} />
        </label>
        <button type="submit" disabled={busy || !text.trim()} aria-label="Отправить комментарий">
          Отправить
        </button>
      </form>
    </section>
  );
}
