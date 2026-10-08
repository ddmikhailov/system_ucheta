import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import StatusMark from "../components/StatusMark";
import { markKind } from "../utils/statusMark";
import AnswerInput from "../components/task/AnswerInput";
import AssignmentThread from "../components/task/AssignmentThread";
import ProgressRing from "../components/task/ProgressRing";
import { COLLECT_MODE_LABELS, REVIEWER_LABELS, TASK_STATUS_LABELS } from "../constants/tasks";
import { useUnsavedWarning } from "../hooks/useUnsavedWarning";
import { formatDateRu, formatDueShort, formatServerDateTimeFull, formatTimeRu } from "../utils/date";
import { relativeDue } from "../utils/deadline";
import { dialogs, toast } from "../utils/feedback";
import { plural } from "../utils/plural";
import { initials, isEmptyValue, localProblem, missingRequired, rowComplete, valueText } from "../utils/taskAnswers";
import type { AnswerField, Values } from "../utils/taskAnswers";
import type { AssignmentDetail } from "../api/types";
import TextArea from "../components/TextArea";

type RowState = { is_included: boolean; values: Values };
type Filter = "all" | "empty" | "flagged";
type SaveState = "idle" | "pending" | "saving" | "saved" | "invalid" | "error";

const AUTOSAVE_MS = 1500;
// Несохранённые правки на случай ухода внутри приложения (меню, колокольчик), когда автосохранение
// не прошло: при возвращении на задачу они подставятся снова. Только в этой вкладке браузера.
const draftKey = (id: string | undefined) => `task-draft-${id}`;

function readDraft(id: string | undefined): { rows: Record<number, RowState>; groupValues: Values } | null {
  try {
    const raw = window.sessionStorage.getItem(draftKey(id));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeDraft(id: string | undefined, draft: { rows: Record<number, RowState>; groupValues: Values } | null) {
  try {
    if (draft) window.sessionStorage.setItem(draftKey(id), JSON.stringify(draft));
    else window.sessionStorage.removeItem(draftKey(id));
  } catch {
    // Хранилище недоступно (приватный режим) — остаётся предупреждение браузера при закрытии вкладки.
  }
}
const STUDENTS: [string, string, string] = ["студента", "студентов", "студентов"];


/** Заполнить столбец разом: «всем без кружков — не посещает». */
function FillColumn({
  fields,
  targets,
  onApply,
  onClose,
}: {
  fields: AnswerField[];
  targets: { id: number; values: Values }[];
  onApply: (key: string, value: unknown, overwrite: boolean) => void;
  onClose: () => void;
}) {
  const [key, setKey] = useState(fields[0]?.key ?? "");
  const [value, setValue] = useState<unknown>(null);
  const [overwrite, setOverwrite] = useState(false);
  const field = fields.find((f) => f.key === key);
  if (!field) return null;
  const count = targets.filter((t) => overwrite || isEmptyValue(t.values[key])).length;
  const problem = localProblem(field, value);
  return (
    <div className="fill-column" role="group" aria-label="Заполнить столбец">
      <label className="form-field">
        Поле
        <select
          value={key}
          onChange={(e) => {
            setKey(e.target.value);
            setValue(null);
          }}
        >
          {fields.map((f) => (
            <option key={f.key} value={f.key}>
              {f.label}
            </option>
          ))}
        </select>
      </label>
      <div className="form-field">
        Значение
        <AnswerInput field={field} value={value} onChange={setValue} label={`Значение для всех: ${field.label}`} invalid={!!problem} />
      </div>
      <label className="filter-check">
        <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} /> Заменить и уже заполненные
      </label>
      <div className="fill-column__actions">
        <button type="button" className="btn-secondary" onClick={onClose}>
          Отмена
        </button>
        <button
          type="button"
          className="btn-primary"
          disabled={count === 0 || isEmptyValue(value) || !!problem}
          onClick={() => {
            onApply(key, value, overwrite);
            onClose();
          }}
        >
          Заполнить {count} {plural(count, ["студенту", "студентам", "студентам"])}
        </button>
      </div>
    </div>
  );
}

// Заполнение назначения куратором (автосохранение черновика → отправка) и проверка: принять / вернуть.
export default function TaskAssignmentPage() {
  const { assignmentId } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<AssignmentDetail | null>(null);
  const [groupValues, setGroupValues] = useState<Values>({});
  const [rows, setRows] = useState<Record<number, RowState>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reviewComment, setReviewComment] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [fillOpen, setFillOpen] = useState(false);
  // Строки, подставленные из досье при открытии: метка держится, пока куратор их не тронул
  // (автосохранение записывает все строки, и сервер после него уже не отличит подставленное).
  const [fromDossier, setFromDossier] = useState<Set<number>>(new Set());

  // Автосохранение: каждая правка увеличивает версию; сохранение помнит, какую версию отправило.
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [editTick, setEditTick] = useState(0);
  const version = useRef(0);
  const savedVersion = useRef(0);
  const inflight = useRef<Promise<boolean> | null>(null);
  const stateRef = useRef({ rows, groupValues, detail });
  useLayoutEffect(() => {
    stateRef.current = { rows, groupValues, detail };
  });

  const apply = useCallback((d: AssignmentDetail) => {
    setDetail(d);
    setGroupValues(d.group_values);
    setRows(Object.fromEntries(d.rows.map((r) => [r.student_id, { is_included: r.is_included, values: r.values }])));
  }, []);

  const load = useCallback(() => {
    api
      .get<AssignmentDetail>(`/tasks/assignments/${assignmentId}`)
      .then((d) => {
        apply(d);
        setFromDossier(new Set(d.rows.filter((r) => r.from_dossier).map((r) => r.student_id)));
        version.current = 0;
        savedVersion.current = 0;
        setError(null);
        const draft = d.can_edit ? readDraft(assignmentId) : null;
        if (draft) {
          setRows((prev) => ({ ...prev, ...draft.rows }));
          setGroupValues((prev) => ({ ...prev, ...draft.groupValues }));
          version.current = 1;
          setSaveState("pending");
          setEditTick((t) => t + 1);
          toast("Восстановлены несохранённые правки — они сохранятся сами", "info");
        } else if (!d.can_edit) {
          writeDraft(assignmentId, null);
        }
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить задачу"));
  }, [assignmentId, apply]);

  useEffect(load, [load]);

  const flush = useCallback(async (): Promise<boolean> => {
    if (inflight.current) await inflight.current;
    const { rows: r, groupValues: g, detail: d } = stateRef.current;
    if (!d || savedVersion.current === version.current) return true;
    const perStudent = d.collect_mode !== "group";
    const problem = d.fields
      .map((f) => {
        const values = perStudent ? Object.values(r).filter((x) => x.is_included).map((x) => x.values[f.key]) : [g[f.key]];
        const bad = values.map((v) => localProblem(f, v)).find(Boolean);
        return bad ? `«${f.label}»: ${bad}` : null;
      })
      .find(Boolean);
    if (problem) {
      setSaveState("invalid");
      setSaveMessage(`Не сохранено: ${problem}`);
      return false;
    }
    const sent = version.current;
    const payload = perStudent
      ? {
          group_values: {},
          rows: Object.entries(r).map(([id, x]) => ({ student_id: Number(id), is_included: x.is_included, values: x.values })),
        }
      : { group_values: g, rows: [] };
    setSaveState("saving");
    const request = api
      .put<AssignmentDetail>(`/tasks/assignments/${d.id}/answers`, payload)
      .then((fresh) => {
        savedVersion.current = sent;
        if (version.current === sent) {
          apply(fresh);
          setSaveState("saved");
        } else {
          // Пока сохраняли, куратор продолжил: свежие правки не затираем, обновляем только сведения о задаче.
          setDetail({ ...fresh, rows: stateRef.current.detail?.rows ?? fresh.rows });
          setSaveState("pending");
        }
        setSaveMessage(null);
        setSavedAt(new Date());
        return true;
      })
      .catch((err) => {
        setSaveState("error");
        setSaveMessage(`Не сохранено: ${err instanceof ApiError ? err.message : "нет связи с сервером"}`);
        return false;
      })
      .finally(() => {
        inflight.current = null;
      });
    inflight.current = request;
    return request;
  }, [apply]);

  useEffect(() => {
    if (editTick === 0) return;
    const timer = window.setTimeout(() => void flush(), AUTOSAVE_MS);
    return () => window.clearTimeout(timer);
  }, [editTick, flush]);

  // Уход внутри приложения (ссылка, «Назад») — дописываем черновик в фоне.
  const flushRef = useRef(flush);
  useLayoutEffect(() => {
    flushRef.current = flush;
  });
  useEffect(
    () => () => {
      if (savedVersion.current !== version.current) void flushRef.current();
    },
    []
  );

  const unsaved = saveState === "pending" || saveState === "saving" || saveState === "invalid" || saveState === "error";
  useUnsavedWarning(unsaved);

  useEffect(() => {
    if (!detail?.can_edit) return;
    writeDraft(assignmentId, unsaved ? { rows, groupValues } : null);
  }, [assignmentId, detail?.can_edit, unsaved, rows, groupValues]);

  if (!detail) return error ? <div className="error-text">{error}</div> : <p className="hint">Загрузка…</p>;

  const editable = detail.can_edit;
  const perStudent = detail.collect_mode !== "group";
  const selectedMode = detail.collect_mode === "selected";
  const base = `/tasks/assignments/${detail.id}`;
  const fields = detail.fields;

  function edited() {
    version.current += 1;
    setSaveState("pending");
    setSaveMessage(null);
    setEditTick((t) => t + 1);
  }

  function setRowValue(studentId: number, key: string, value: unknown) {
    setRows((prev) => ({ ...prev, [studentId]: { ...prev[studentId], values: { ...prev[studentId]?.values, [key]: value } } }));
    if (fromDossier.has(studentId)) setFromDossier((prev) => new Set([...prev].filter((id) => id !== studentId)));
    edited();
  }

  function setIncluded(studentId: number, included: boolean) {
    setRows((prev) => ({ ...prev, [studentId]: { values: prev[studentId]?.values ?? {}, is_included: included } }));
    edited();
  }

  function setGroupValue(key: string, value: unknown) {
    setGroupValues((prev) => ({ ...prev, [key]: value }));
    edited();
  }

  // Строки, к которым относятся счётчики и «заполнить столбец».
  const counted = detail.rows.filter((r) => !selectedMode || rows[r.student_id]?.is_included);
  const doneRows = counted.filter((r) => rowComplete(fields, rows[r.student_id]?.values ?? {}));
  const commentsByStudent = new Map<number, string[]>();
  for (const c of detail.comments) {
    if (c.student_id != null) commentsByStudent.set(c.student_id, [...(commentsByStudent.get(c.student_id) ?? []), c.text]);
  }
  const groupMissing = missingRequired(fields, groupValues);
  const groupFilled = fields.filter((f) => !isEmptyValue(groupValues[f.key])).length;
  // Отправку держим только то, что не пропустит и сервер: пустые обязательные поля (или совсем пустой
  // групповой ответ). Необязательные поля можно оставить пустыми.
  const hasRequired = fields.some((f) => f.required);
  const blocking = perStudent
    ? counted.filter((r) => missingRequired(fields, rows[r.student_id]?.values ?? {}).length > 0).length
    : groupMissing.length + (!hasRequired && groupFilled === 0 ? 1 : 0);
  // Совсем пустой ответ по студентам сервер не примет («нет ответа»).
  const nothingYet = perStudent && counted.length > 0 && doneRows.length === 0;

  function submitHint(): string {
    if (blocking > 0) {
      if (perStudent) return `Обязательные поля пусты у ${blocking} ${plural(blocking, STUDENTS)}`;
      return groupMissing.length > 0 ? `Не заполнено: ${groupMissing.join(", ")}` : "Заполните хотя бы одно поле";
    }
    if (nothingYet) return "Заполните ответы, чтобы отправить";
    if (!perStudent || counted.length === 0) return "";
    const left = counted.length - doneRows.length;
    return left > 0 ? `Без ответа: ${left} из ${counted.length}, можно отправлять` : `Заполнено: ${counted.length} из ${counted.length}`;
  }

  const shown = detail.rows.filter((r) => {
    const state = rows[r.student_id];
    if (filter === "empty") return (!selectedMode || state?.is_included) && !rowComplete(fields, state?.values ?? {});
    if (filter === "flagged") return commentsByStudent.has(r.student_id);
    return true;
  });

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (!(await flush())) return;
      const d = await api.post<AssignmentDetail>(`${base}/submit`);
      apply(d);
      setSaveState("idle");
      toast(d.status === "accepted" ? "Задача принята" : "Отправлено на проверку");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Не удалось отправить";
      setError(message);
      toast(message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function review(action: "accept" | "return") {
    if (action === "return" && !reviewComment.trim()) {
      setError("Напишите, что исправить: без комментария вернуть нельзя");
      toast("Напишите, что исправить: без комментария вернуть нельзя", "error");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const d = await api.post<AssignmentDetail>(`${base}/review`, { action, comment: reviewComment || null });
      apply(d);
      setReviewComment("");
      toast(action === "accept" ? "Принято" : "Возвращено на доработку");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Не удалось выполнить операцию";
      setError(message);
      toast(message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function addComment(text: string, studentId: number | null): Promise<boolean> {
    setBusy(true);
    try {
      await api.post(`${base}/comments`, { text, student_id: studentId });
      const fresh = await api.get<AssignmentDetail>(base);
      // Черновик не трогаем — подтягиваем только обсуждение.
      setDetail((prev) => (prev ? { ...prev, comments: fresh.comments, history: fresh.history } : fresh));
      return true;
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Не удалось отправить комментарий", "error");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function goBack() {
    if (unsaved && !(await flush())) {
      const leave = await dialogs.confirm("Черновик не сохранён. Уйти без сохранения последних правок?", {
        confirmLabel: "Уйти",
        cancelLabel: "Остаться",
      });
      if (!leave) return;
      version.current = savedVersion.current;
      writeDraft(assignmentId, null);
    }
    if (window.history.length > 1) navigate(-1);
    else navigate("/");
  }

  if (detail.kind === "meal") {
    // «Подать питание» заполняется не формой задачи, а во вкладке «Питание» группы; подача закрывает задачу сама.
    const done = detail.status === "accepted";
    return (
      <div className="assignment">
        <p>
          <button className="link-btn" onClick={goBack}>
            ← Назад
          </button>
        </p>
        <h2>{detail.title}</h2>
        {detail.description && <p>{detail.description}</p>}
        <div className={`day-status ${done ? "submitted" : "not-submitted"}`}>
          {done ? "Питание подано." : `Питание не подано. Срок — ${formatDueShort(detail.due_date)} 16:00.`}
        </div>
        <p>
          <Link className="btn-primary" to={`/cabinet/groups/${detail.study_group_id}?tab=meals`}>
            Открыть вкладку «Питание»
          </Link>
        </p>
      </div>
    );
  }

  const studentNames = new Map(detail.rows.map((r) => [r.student_id, r.student_name]));
  const statusLabel =
    TASK_STATUS_LABELS[detail.status] +
    (detail.status === "submitted" && detail.review_steps > 1 ? ` (ступень ${detail.review_step} из ${detail.review_steps})` : "");
  const kind = markKind(detail);
  const days = relativeDue(detail.due_date);
  const submitLabel = detail.reviewer_rule === "none" ? "Отправить" : "Отправить на проверку";
  const ringDone = perStudent ? doneRows.length : groupFilled;
  const ringTotal = perStudent ? counted.length : fields.length;

  let saveText = "";
  if (saveState === "saving") saveText = "Сохраняется…";
  else if (saveState === "pending") saveText = "Есть несохранённые правки";
  else if (saveState === "saved" && savedAt) saveText = `Сохранено в ${formatTimeRu(savedAt)}`;
  else if (saveMessage) saveText = saveMessage;

  // Да/нет занимает мало места, выбор из списка и текст — сколько дадут.
  const gridStyle = {
    "--answer-template": fields.map((f) => (f.type === "bool" ? "max-content" : f.type === "date" ? "150px" : "minmax(160px, 1fr)")).join(" "),
  } as CSSProperties;

  return (
    <div className="assignment">
      <p>
        <button className="link-btn" onClick={goBack}>
          ← Назад
        </button>
      </p>

      <header className="assignment__head">
        <div className="assignment__title">
          <div className="assignment__meta">
            <span className="group-chip">{detail.group_code}</span>
            <span className={detail.is_overdue ? "is-hot" : ""}>
              срок {formatDueShort(detail.due_date)}, {detail.status === "accepted" ? formatDateRu(detail.due_date) : days}
            </span>
            {detail.step_total ? <span>шаг {detail.step_no} из {detail.step_total}</span> : null}
          </div>
          <h2>{detail.title}</h2>
          <div className="assignment__meta">
            <StatusMark kind={kind} withLabel label={kind === "overdue" ? `${statusLabel}, просрочено` : statusLabel} />
            <span>{COLLECT_MODE_LABELS[detail.collect_mode]}</span>
            <span>проверяет: {REVIEWER_LABELS[detail.reviewer_rule]}</span>
          </div>
        </div>
        {!detail.is_locked && ringTotal > 0 && (
          <ProgressRing
            done={ringDone}
            total={ringTotal}
            label={`Заполнено ${ringDone} из ${ringTotal}${perStudent ? "" : " полей"}`}
          />
        )}
      </header>

      {detail.status === "accepted" && detail.reviewed_at && (
        <p className="hint">
          Принято {formatServerDateTimeFull(detail.reviewed_at)}
          {detail.reviewed_by_name ? `, проверил(а): ${detail.reviewed_by_name}` : " без проверки"}
        </p>
      )}
      {detail.is_locked && detail.locked_reason && <div className="callout">{detail.locked_reason}</div>}
      {detail.status === "returned" && detail.review_comment && (
        <div className="callout callout--hot" role="note">
          <b>Вернули на доработку</b>
          <span>{detail.review_comment}</span>
        </div>
      )}
      {detail.description && <p className="assignment__description">{detail.description}</p>}
      {error && (
        <div className="error-text" role="alert">
          {error}
        </div>
      )}

      {detail.can_review && (
        <section className="review-panel" aria-label="Проверка">
          <h3>Ваше решение</h3>
          <label className="form-field" htmlFor="review-comment">
            Комментарий проверяющего
          </label>
          <TextArea
            id="review-comment"
            rows={2}
            placeholder="Что исправить (обязательно, если возвращаете)"
            value={reviewComment}
            onChange={(e) => setReviewComment(e.target.value)}
          />
          <div className="review-panel__actions">
            <button className="btn-primary" onClick={() => review("accept")} disabled={busy}>
              Принять
            </button>
            <button className="danger-btn" onClick={() => review("return")} disabled={busy}>
              Вернуть на доработку
            </button>
          </div>
        </section>
      )}

      {!perStudent ? (
        <div className="group-answer">
          {fields.map((f) => (
            <div key={f.key} className="group-answer__field">
              <span className="group-answer__label">
                {f.label}
                {f.required && <span className="required-mark"> обязательно</span>}
              </span>
              {editable ? (
                <AnswerInput
                  field={f}
                  value={groupValues[f.key]}
                  onChange={(v) => setGroupValue(f.key, v)}
                  label={f.label}
                  invalid={!!localProblem(f, groupValues[f.key])}
                />
              ) : (
                <span className="answer-value">{valueText(f, groupValues[f.key])}</span>
              )}
            </div>
          ))}
        </div>
      ) : (
        <>
          <div className="roster-tools">
            <div className="segmented" role="group" aria-label="Кого показать">
              <button aria-pressed={filter === "all"} className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>
                Все {detail.rows.length}
              </button>
              <button aria-pressed={filter === "empty"} className={filter === "empty" ? "active" : ""} onClick={() => setFilter("empty")}>
                Не заполнены {counted.length - doneRows.length}
              </button>
              {commentsByStudent.size > 0 && (
                <button
                 
                  aria-pressed={filter === "flagged"}
                  className={filter === "flagged" ? "active" : ""}
                  onClick={() => setFilter("flagged")}
                >
                  С замечаниями {commentsByStudent.size}
                </button>
              )}
            </div>
            {editable && counted.length > 0 && (
              <button type="button" className="btn-secondary" aria-expanded={fillOpen} onClick={() => setFillOpen((v) => !v)}>
                Заполнить столбец
              </button>
            )}
          </div>
          {fillOpen && (
            <FillColumn
              fields={fields}
              targets={counted.map((r) => ({ id: r.student_id, values: rows[r.student_id]?.values ?? {} }))}
              onClose={() => setFillOpen(false)}
              onApply={(key, value, overwrite) => {
                setRows((prev) => {
                  const next = { ...prev };
                  for (const r of counted) {
                    const state = next[r.student_id] ?? { is_included: true, values: {} };
                    if (overwrite || isEmptyValue(state.values[key])) next[r.student_id] = { ...state, values: { ...state.values, [key]: value } };
                  }
                  return next;
                });
                edited();
              }}
            />
          )}

          <div className="answer-grid" style={gridStyle}>
            <div className="answer-grid__head" aria-hidden="true">
              <span />
              <span>Студент</span>
              {fields.map((f) => (
                <span key={f.key}>
                  {f.label}
                  {f.required && <span className="required-mark"> обязательно</span>}
                </span>
              ))}
            </div>
            {shown.map((r) => {
              const state = rows[r.student_id] ?? { is_included: r.is_included, values: {} };
              const active = !selectedMode || state.is_included;
              const complete = active && rowComplete(fields, state.values);
              const remarks = commentsByStudent.get(r.student_id);
              return (
                <div
                  key={r.student_id}
                  className={`answer-row${remarks ? " is-flagged" : ""}${active ? "" : " is-excluded"}${complete ? " is-complete" : ""}`}
                >
                  <span className="avatar" aria-hidden="true">
                    {initials(r.student_name)}
                  </span>
                  <div className="answer-row__who">
                    <span className="answer-row__name">{r.student_name}</span>
                    {selectedMode && (
                      <label className="filter-check">
                        <input
                          type="checkbox"
                          disabled={!editable}
                          checked={state.is_included}
                          onChange={(e) => setIncluded(r.student_id, e.target.checked)}
                        />{" "}
                        касается
                      </label>
                    )}
                    {remarks && <span className="answer-row__remark">Замечание: {remarks[remarks.length - 1]}</span>}
                    {!remarks && fromDossier.has(r.student_id) && editable && <span className="answer-row__dossier">из досье, проверьте</span>}
                    {!remarks && active && !complete && editable && !fromDossier.has(r.student_id) && <span className="answer-row__todo">не заполнено</span>}
                  </div>
                  {fields.map((f) => (
                    <div key={f.key} className="answer-row__cell">
                      <span className="answer-row__label" aria-hidden="true">
                        {f.label}
                      </span>
                      {!active ? (
                        <span className="answer-value">—</span>
                      ) : editable ? (
                        <AnswerInput
                          field={f}
                          value={state.values[f.key]}
                          onChange={(v) => setRowValue(r.student_id, f.key, v)}
                          label={`${f.label}: ${r.student_name}`}
                          invalid={!!localProblem(f, state.values[f.key])}
                        />
                      ) : (
                        <span className="answer-value">{valueText(f, state.values[f.key])}</span>
                      )}
                    </div>
                  ))}
                </div>
              );
            })}
            {shown.length === 0 && (
              <p className="empty-state">{filter === "empty" ? "Все заполнены — можно отправлять." : "Никого с замечаниями."}</p>
            )}
          </div>
        </>
      )}

      {editable && (
        <div className="submit-bar">
          <span className={`submit-bar__save submit-bar__save--${saveState}`} role="status">
            {saveText}
          </span>
          <span className="submit-bar__left">
            {submitHint()}
          </span>
          <button className="btn-primary" onClick={submit} disabled={busy || !detail.can_submit || blocking > 0 || nothingYet}>
            {submitLabel}
          </button>
        </div>
      )}

      <AssignmentThread
        history={detail.history}
        comments={detail.comments}
        reviewSteps={detail.review_steps}
        studentNames={studentNames}
        students={perStudent ? detail.rows.map((r) => ({ id: r.student_id, name: r.student_name })) : []}
        busy={busy}
        onComment={addComment}
      />
    </div>
  );
}
