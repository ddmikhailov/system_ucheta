import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useScrollToTopOnChange } from "../hooks/useScrollToTopOnChange";
import { COLLECT_MODE_LABELS, HISTORY_LABELS, REVIEWER_LABELS, TASK_STATUS_LABELS } from "../constants/tasks";
import { formatDateRu, formatServerDateTimeFull } from "../utils/date";
import type { AssignmentDetail } from "../api/types";

type Values = Record<string, unknown>;
type RowState = { is_included: boolean; values: Values };

function FieldInput({
  field,
  value,
  disabled,
  onChange,
}: {
  field: AssignmentDetail["fields"][number];
  value: unknown;
  disabled: boolean;
  onChange: (v: unknown) => void;
}) {
  switch (field.type) {
    case "bool":
      return (
        <input type="checkbox" disabled={disabled} checked={value === true} onChange={(e) => onChange(e.target.checked)} />
      );
    case "select":
      return (
        <select disabled={disabled} value={typeof value === "string" ? value : ""} onChange={(e) => onChange(e.target.value)}>
          <option value="">—</option>
          {field.options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      );
    case "multiselect": {
      const selected = Array.isArray(value) ? (value as string[]) : [];
      return (
        <span className="task-multiselect">
          {field.options.map((o) => (
            <label key={o} style={{ marginRight: 10, whiteSpace: "nowrap" }}>
              <input
                type="checkbox"
                disabled={disabled}
                checked={selected.includes(o)}
                onChange={(e) => onChange(e.target.checked ? [...selected, o] : selected.filter((x) => x !== o))}
              />{" "}
              {o}
            </label>
          ))}
        </span>
      );
    }
    case "date":
      return <input type="date" disabled={disabled} value={typeof value === "string" ? value : ""} onChange={(e) => onChange(e.target.value)} />;
    case "number":
      return (
        <input type="number" step="any" disabled={disabled} value={value === undefined || value === null ? "" : String(value)} onChange={(e) => onChange(e.target.value)} />
      );
    case "link":
      return (
        <input
          type="url"
          placeholder="https://…"
          disabled={disabled}
          value={typeof value === "string" ? value : ""}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    default:
      return <input type="text" disabled={disabled} value={typeof value === "string" ? value : ""} onChange={(e) => onChange(e.target.value)} />;
  }
}

// Заполнение назначения куратором (черновик → отправка) и проверка: принять / вернуть.
export default function TaskAssignmentPage() {
  const { assignmentId } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<AssignmentDetail | null>(null);
  const [groupValues, setGroupValues] = useState<Values>({});
  const [rows, setRows] = useState<Record<number, RowState>>({});
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useScrollToTopOnChange(error, notice);
  const [reviewComment, setReviewComment] = useState("");
  const [commentText, setCommentText] = useState("");
  const [commentStudent, setCommentStudent] = useState("");

  const apply = useCallback((d: AssignmentDetail) => {
    setDetail(d);
    setGroupValues(d.group_values);
    setRows(Object.fromEntries(d.rows.map((r) => [r.student_id, { is_included: r.is_included, values: r.values }])));
    setDirty(false);
  }, []);

  const load = useCallback(() => {
    api
      .get<AssignmentDetail>(`/tasks/assignments/${assignmentId}`)
      .then((d) => {
        apply(d);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить задачу"));
  }, [assignmentId, apply]);

  useEffect(load, [load]);

  if (!detail) return error ? <div className="error-text">{error}</div> : <p className="hint">Загрузка…</p>;

  const editable = detail.can_edit;
  const perStudent = detail.collect_mode !== "group";
  const base = `/tasks/assignments/${detail.id}`;

  async function run<T>(action: () => Promise<T>, onOk: (v: T) => void) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      onOk(await action());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось выполнить операцию");
    } finally {
      setBusy(false);
    }
  }

  function answersPayload() {
    if (!perStudent) return { group_values: groupValues, rows: [] };
    const changed = Object.entries(rows).map(([id, r]) => ({
      student_id: Number(id),
      is_included: r.is_included,
      values: r.values,
    }));
    return { group_values: {}, rows: changed };
  }

  const save = () =>
    run(() => api.put<AssignmentDetail>(`${base}/answers`, answersPayload()), (d) => {
      apply(d);
      setNotice("Черновик сохранён");
    });

  async function submit() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (dirty) apply(await api.put<AssignmentDetail>(`${base}/answers`, answersPayload()));
      const d = await api.post<AssignmentDetail>(`${base}/submit`);
      apply(d);
      setNotice(d.status === "accepted" ? "Задача принята" : "Отправлено на проверку");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось отправить");
    } finally {
      setBusy(false);
    }
  }

  const review = (action: "accept" | "return") =>
    run(() => api.post<AssignmentDetail>(`${base}/review`, { action, comment: reviewComment || null }), (d) => {
      apply(d);
      setReviewComment("");
      setNotice(action === "accept" ? "Принято" : "Возвращено на доработку");
    });

  async function addComment(e: FormEvent) {
    e.preventDefault();
    if (!commentText.trim()) return;
    await run(() => api.post(`${base}/comments`, { text: commentText, student_id: commentStudent ? Number(commentStudent) : null }), () => {
      setCommentText("");
      setCommentStudent("");
      load();
    });
  }

  function setRowValue(studentId: number, key: string, value: unknown) {
    setRows((prev) => ({ ...prev, [studentId]: { ...prev[studentId], values: { ...prev[studentId]?.values, [key]: value } } }));
    setDirty(true);
  }

  function setIncluded(studentId: number, included: boolean) {
    setRows((prev) => ({ ...prev, [studentId]: { values: prev[studentId]?.values ?? {}, is_included: included } }));
    setDirty(true);
  }

  const studentNames = new Map(detail.rows.map((r) => [r.student_id, r.student_name]));

  return (
    <div className="student-card">
      <p>
        <button className="link-btn" onClick={() => (window.history.length > 1 ? navigate(-1) : navigate("/"))}>
          ← Назад
        </button>
      </p>
      <div className="student-card__header">
        <h2>{detail.title}</h2>
        <span className={`locked-badge${detail.status === "accepted" ? "" : " risk-badge"}`}>
          {TASK_STATUS_LABELS[detail.status] ?? detail.status}
          {detail.status === "submitted" && detail.review_steps > 1 && ` (ступень ${detail.review_step} из ${detail.review_steps})`}
        </span>
        {detail.is_overdue && <span className="locked-badge risk-badge">просрочено</span>}
      </div>
      <p className="hint">
        Группа {detail.group_code} · срок {formatDateRu(detail.due_date)} ·{" "}
        {COLLECT_MODE_LABELS[detail.collect_mode]} · проверяет: {REVIEWER_LABELS[detail.reviewer_rule]}
      </p>
      {detail.status === "accepted" && detail.reviewed_at && (
        <p className="hint">
          Принято {formatServerDateTimeFull(detail.reviewed_at)}
          {detail.reviewed_by_name ? `, проверил(а): ${detail.reviewed_by_name}` : " без проверки"}
        </p>
      )}
      {detail.step_total && (
        <p className="hint">
          Шаг {detail.step_no} из {detail.step_total}
        </p>
      )}
      {detail.is_locked && detail.locked_reason && <div className="day-status not-submitted">{detail.locked_reason}</div>}
      {detail.description && <p style={{ whiteSpace: "pre-wrap" }}>{detail.description}</p>}
      {detail.status === "returned" && detail.review_comment && (
        <div className="error-text">Возвращено на доработку: {detail.review_comment}</div>
      )}
      {error && <div className="error-text">{error}</div>}
      {notice && <div className="day-status submitted">{notice}</div>}

      {!perStudent ? (
        <div className="add-block">
          {detail.fields.map((f) => (
            <p key={f.key}>
              <label>
                {f.label}
                {f.required && " *"}
                <br />
                <FieldInput
                  field={f}
                  value={groupValues[f.key]}
                  disabled={!editable}
                  onChange={(v) => {
                    setGroupValues((prev) => ({ ...prev, [f.key]: v }));
                    setDirty(true);
                  }}
                />
              </label>
            </p>
          ))}
        </div>
      ) : (
        <table className="dash-table roster-table">
          <thead>
            <tr>
              {detail.collect_mode === "selected" && <th>Касается</th>}
              <th>Студент</th>
              {detail.fields.map((f) => (
                <th key={f.key}>
                  {f.label}
                  {f.required && " *"}
                  {f.dossier_field && (
                    <span className="hint" title="Из досье подставлено текущее значение; после приёмки ответ запишется в досье">
                      {" "}
                      (досье)
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {detail.rows.map((r) => {
              const state = rows[r.student_id] ?? { is_included: r.is_included, values: {} };
              const active = detail.collect_mode === "student" || state.is_included;
              return (
                <tr key={r.student_id}>
                  {detail.collect_mode === "selected" && (
                    <td data-label="Касается">
                      <input
                        type="checkbox"
                        disabled={!editable}
                        checked={state.is_included}
                        onChange={(e) => setIncluded(r.student_id, e.target.checked)}
                      />
                    </td>
                  )}
                  <td data-label="Студент">{r.student_name}</td>
                  {detail.fields.map((f) => (
                    <td key={f.key} data-label={f.label}>
                      {active ? (
                        <FieldInput
                          field={f}
                          value={state.values[f.key]}
                          disabled={!editable}
                          onChange={(v) => setRowValue(r.student_id, f.key, v)}
                        />
                      ) : (
                        "—"
                      )}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {editable && (
        <p className="actions-sticky-mobile">
          <button onClick={save} disabled={busy || !dirty}>
            Сохранить черновик
          </button>{" "}
          <button onClick={submit} disabled={busy || !detail.can_submit}>
            Отправить на проверку
          </button>
        </p>
      )}

      {detail.can_review && (
        <div className="add-block">
          <p className="add-block__title">Проверка</p>
          <textarea
            rows={2}
            style={{ width: "100%" }}
            placeholder="Комментарий (обязателен, если возвращаете на доработку)"
            value={reviewComment}
            onChange={(e) => setReviewComment(e.target.value)}
          />
          <p>
            <button onClick={() => review("accept")} disabled={busy}>
              Принять
            </button>{" "}
            <button className="danger-btn" onClick={() => review("return")} disabled={busy}>
              Вернуть на доработку
            </button>
          </p>
        </div>
      )}

      {detail.history.length > 0 && (
        <>
          <h3 className="student-card__section">Ход проверки</h3>
          <ul className="hint" style={{ listStyle: "none", padding: 0 }}>
            {detail.history.map((e, i) => (
              <li key={i} style={{ marginBottom: 4 }}>
                {formatServerDateTimeFull(e.at)} — <b>{HISTORY_LABELS[e.kind] ?? e.kind}</b>
                {e.step != null && detail.review_steps > 1 && ` (ступень ${e.step} из ${detail.review_steps})`}
                {e.user_name && ` · ${e.user_name}`}
              </li>
            ))}
          </ul>
        </>
      )}

      <h3 className="student-card__section">Комментарии</h3>
      {detail.comments.length === 0 ? (
        <p className="hint">Комментариев нет.</p>
      ) : (
        <ul className="hint" style={{ listStyle: "none", padding: 0 }}>
          {detail.comments.map((c) => (
            <li key={c.id} style={{ marginBottom: 6 }}>
              <b>{c.author_name ?? "—"}</b> · {formatServerDateTimeFull(c.created_at)}
              {c.student_id && <> · {studentNames.get(c.student_id) ?? "студент"}</>}: {c.text}
            </li>
          ))}
        </ul>
      )}
      <form className="inline-form" onSubmit={addComment}>
        {perStudent && (
          <select value={commentStudent} onChange={(e) => setCommentStudent(e.target.value)} aria-label="К кому комментарий">
            <option value="">Ко всему ответу</option>
            {detail.rows.map((r) => (
              <option key={r.student_id} value={r.student_id}>
                {r.student_name}
              </option>
            ))}
          </select>
        )}
        <input
          placeholder="Написать комментарий"
          value={commentText}
          onChange={(e) => setCommentText(e.target.value)}
          style={{ flex: 1, minWidth: 200 }}
        />
        <button type="submit" disabled={busy}>
          Отправить
        </button>
      </form>
    </div>
  );
}
