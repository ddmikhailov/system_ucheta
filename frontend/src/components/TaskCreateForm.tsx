import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { COLLECT_MODE_LABELS, FIELD_TYPE_LABELS, REVIEWER_LABELS } from "../constants/tasks";
import { formatDueShort, todayIso } from "../utils/date";
import { relativeDue } from "../utils/deadline";
import { dialogs, toast } from "../utils/feedback";
import { plural } from "../utils/plural";
import type { AnswerField } from "../utils/taskAnswers";
import type { DepartmentAdmin, DossierTarget, StudyGroupAdmin, TaskDetail, TaskField, TaskFieldType, TaskTemplate } from "../api/types";
import { DEPARTMENT_SCOPED_ROLES, inRoles } from "../constants/roles";
import FilterableMultiSelect from "./FilterableMultiSelect";
import AnswerInput from "./task/AnswerInput";

type ScopeKind = "all" | "departments" | "courses" | "groups";
type Step = 0 | 1 | 2 | 3;

interface FieldDraft {
  label: string;
  type: TaskFieldType;
  required: boolean;
  optionsText: string;
  dossierField: string;
}

interface ScopePreview {
  groups: number;
  students: number;
  curators: number;
  without_curator: string[];
}

const EMPTY_FIELD: FieldDraft = { label: "", type: "text", required: false, optionsText: "", dossierField: "" };
const FUNDING_OPTIONS = "бюджет, договор";
const STEPS = ["Что сделать", "Кому", "Форма ответа", "Срок и проверка"];

const MODE_HINTS: Record<string, string> = {
  group: "Один ответ от группы: видеовизитка, план работы.",
  student: "Строка на каждого студента: кружки, согласия, справки. Поля можно связать с досье.",
  selected: "Куратор сам отмечает, кого задача касается, и заполняет только их.",
};

export interface AfterTask {
  id: number;
  title: string;
  due_date: string;
}

const splitOptions = (text: string) =>
  text
    .split(",")
    .map((o) => o.trim())
    .filter(Boolean);

// Создание задачи — мастер из четырёх шагов: что сделать → кому → форма ответа → срок и проверка.
// Справа — как задачу увидит куратор. Режим «следующий шаг»: охват берётся у предыдущего шага,
// срок не раньше его срока, выбирается момент открытия.
export default function TaskCreateForm({ onCreated, afterTask }: { onCreated: (task: TaskDetail) => void; afterTask?: AfterTask | null }) {
  const { user } = useAuth();
  const scopedToDepartment = inRoles(user?.role, DEPARTMENT_SCOPED_ROLES);
  const minDue = afterTask && afterTask.due_date > todayIso() ? afterTask.due_date : todayIso();
  const [step, setStep] = useState<Step>(0);
  const [visited, setVisited] = useState<Step>(0);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [mode, setMode] = useState("student");
  const [reviewer, setReviewer] = useState("dept_head");
  const [dueDate, setDueDate] = useState(minDue);
  const [unlockOn, setUnlockOn] = useState("accepted");
  const [fields, setFields] = useState<FieldDraft[]>([{ ...EMPTY_FIELD }]);
  const [scopeKind, setScopeKind] = useState<ScopeKind>("all");
  const [departmentIds, setDepartmentIds] = useState<number[]>([]);
  const [courses, setCourses] = useState<number[]>([]);
  const [groupIds, setGroupIds] = useState<number[]>([]);
  const [excludeIds, setExcludeIds] = useState<number[]>([]);
  const [departments, setDepartments] = useState<DepartmentAdmin[]>([]);
  const [groups, setGroups] = useState<StudyGroupAdmin[]>([]);
  const [targets, setTargets] = useState<DossierTarget[]>([]);
  const [templates, setTemplates] = useState<TaskTemplate[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [preview, setPreview] = useState<ScopePreview | null>(null);
  const [sample, setSample] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get<DepartmentAdmin[]>("/admin/departments").then(setDepartments).catch(() => setDepartments([]));
    api
      .get<StudyGroupAdmin[]>("/admin/groups")
      .then((all) => setGroups(all.filter((g) => g.is_active)))
      .catch(() => setGroups([]));
    api.get<DossierTarget[]>("/tasks/dossier-fields").then(setTargets).catch(() => setTargets([]));
    api.get<TaskTemplate[]>("/tasks/templates").then(setTemplates).catch(() => setTemplates([]));
  }, []);

  const scope = {
    all_groups: scopeKind === "all",
    department_ids: scopeKind === "departments" ? departmentIds : [],
    courses: scopeKind === "courses" ? courses : [],
    group_ids: scopeKind === "groups" ? groupIds : [],
    exclude_group_ids: excludeIds,
  };
  const scopeKey = JSON.stringify(scope);

  // Счётчик охвата: пересчитываем через паузу после изменения выбора.
  useEffect(() => {
    if (afterTask) return;
    const timer = window.setTimeout(() => {
      api
        .post<ScopePreview>("/tasks/scope-preview", JSON.parse(scopeKey))
        .then(setPreview)
        .catch(() => setPreview(null));
    }, 300);
    return () => window.clearTimeout(timer);
  }, [scopeKey, afterTask]);

  const toggle = (list: number[], set: (v: number[]) => void, id: number) =>
    set(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

  const updateField = (i: number, patch: Partial<FieldDraft>) =>
    setFields((prev) => prev.map((f, idx) => (idx === i ? { ...f, ...patch } : f)));

  // Выбор поля досье подстраивает поле формы (тип, название, варианты), а смена типа на несовместимый снимает связь.
  const linkField = (i: number, key: string) => {
    const target = targets.find((t) => t.key === key);
    setFields((prev) =>
      prev.map((f, idx) => {
        if (idx !== i) return f;
        if (!target) return { ...f, dossierField: "" };
        return {
          ...f,
          dossierField: key,
          type: target.types.includes(f.type) ? f.type : target.types[0],
          label: f.label || target.label,
          optionsText: key === "funding" && !f.optionsText ? FUNDING_OPTIONS : f.optionsText,
        };
      })
    );
  };

  const changeType = (i: number, type: TaskFieldType) =>
    setFields((prev) =>
      prev.map((f, idx) => {
        if (idx !== i) return f;
        const target = targets.find((t) => t.key === f.dossierField);
        return { ...f, type, dossierField: target && !target.types.includes(type) ? "" : f.dossierField };
      })
    );

  // Шаблон заполняет форму целиком, кроме срока: его всегда выбирают заново.
  function applyTemplate(id: string) {
    setTemplateId(id);
    const t = templates.find((x) => String(x.id) === id);
    if (!t) return;
    setTitle(t.title);
    setDescription(t.description ?? "");
    setMode(t.collect_mode);
    setReviewer(t.reviewer_rule);
    setFields(
      t.fields.map((f) => ({
        label: f.label,
        type: f.type,
        required: f.required,
        optionsText: f.options.join(", "),
        dossierField: f.dossier_field ?? "",
      }))
    );
    const s = t.scope;
    setScopeKind(s.all_groups ? "all" : s.department_ids.length ? "departments" : s.courses.length ? "courses" : "groups");
    setDepartmentIds(s.department_ids);
    setCourses(s.courses);
    setGroupIds(s.group_ids);
    setExcludeIds(s.exclude_group_ids);
    setError(null);
  }

  async function deleteTemplate(t: TaskTemplate) {
    if (!(await dialogs.confirm(`Удалить шаблон «${t.name}»? Созданные по нему задачи не изменятся.`, { confirmLabel: "Удалить", danger: true }))) return;
    try {
      await api.delete(`/tasks/templates/${t.id}`);
      setTemplates((prev) => prev.filter((x) => x.id !== t.id));
      if (templateId === String(t.id)) setTemplateId("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось удалить шаблон");
    }
  }

  const move = (i: number, delta: number) =>
    setFields((prev) => {
      const j = i + delta;
      if (j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });

  // Что мешает перейти дальше с шага; null — можно.
  function stepProblem(s: Step): string | null {
    if (s === 0 && !title.trim()) return "Назовите задачу";
    if (s === 1 && !afterTask) {
      if (scopeKind === "departments" && departmentIds.length === 0) return "Отметьте хотя бы одно отделение";
      if (scopeKind === "courses" && courses.length === 0) return "Отметьте хотя бы один курс";
      if (scopeKind === "groups" && groupIds.length === 0) return "Выберите хотя бы одну группу";
      if (preview && preview.groups === 0) return "В охват не попала ни одна группа";
    }
    if (s === 2) {
      const unnamed = fields.findIndex((f) => !f.label.trim());
      if (unnamed >= 0) return `Назовите поле ${unnamed + 1}`;
      const noOptions = fields.find((f) => (f.type === "select" || f.type === "multiselect") && splitOptions(f.optionsText).length === 0);
      if (noOptions) return `Перечислите варианты для поля «${noOptions.label}»`;
    }
    if (s === 3 && (!dueDate || dueDate < minDue)) return "Укажите срок не раньше сегодняшнего дня";
    return null;
  }

  function goTo(next: Step) {
    if (next > step) {
      for (let s = step; s < next; s++) {
        const problem = stepProblem(s as Step);
        if (problem) {
          setError(problem);
          setStep(s as Step);
          return;
        }
      }
    }
    setError(null);
    setStep(next);
    setVisited((v) => (next > v ? next : v));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (step < 3) {
      goTo((step + 1) as Step);
      return;
    }
    for (const s of [0, 1, 2, 3] as Step[]) {
      const problem = stepProblem(s);
      if (problem) {
        setError(problem);
        setStep(s);
        return;
      }
    }
    setBusy(true);
    setError(null);
    const payloadFields: TaskField[] = fields.map((f) => ({
      label: f.label,
      type: f.type,
      required: f.required,
      options: f.type === "select" || f.type === "multiselect" ? splitOptions(f.optionsText) : [],
      // В задаче «по группе» ответ не относится к студенту — связать с досье нельзя.
      ...(f.dossierField && mode !== "group" ? { dossier_field: f.dossierField } : {}),
    }));
    try {
      const task = await api.post<TaskDetail>("/tasks", {
        title,
        description: description || null,
        collect_mode: mode,
        reviewer_rule: reviewer,
        due_date: dueDate,
        fields: payloadFields,
        ...(afterTask ? { after_task_id: afterTask.id, unlock_on: unlockOn } : {}),
        scope,
      });
      toast(`Задача «${task.title}» разослана: ${task.progress.total} ${plural(task.progress.total, ["группа", "группы", "групп"])}`);
      onCreated(task);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось создать задачу");
    } finally {
      setBusy(false);
    }
  }

  const previewFields: AnswerField[] = fields
    .filter((f) => f.label.trim())
    .map((f, i) => ({
      key: `p${i}`,
      label: f.label,
      type: f.type,
      required: f.required,
      options: f.type === "select" || f.type === "multiselect" ? splitOptions(f.optionsText) : [],
    }));

  return (
    <div className="wizard">
      <form className="wizard__form" onSubmit={submit} noValidate>
        <div className="wizard__head">
          <h3>{afterTask ? `Следующий шаг после «${afterTask.title}»` : "Новая задача"}</h3>
          <ol className="wizard__steps" aria-label="Шаги создания">
            {STEPS.map((label, i) => (
              <li key={label}>
                <button
                  type="button"
                  className={i === step ? "is-current" : i <= visited ? "is-done" : ""}
                  aria-current={i === step ? "step" : undefined}
                  onClick={() => goTo(i as Step)}
                >
                  {i + 1}. {label}
                </button>
              </li>
            ))}
          </ol>
        </div>

        {step === 0 && (
          <div className="wizard__body">
            {templates.length > 0 && !afterTask && (
              <div className="template-gallery" role="group" aria-label="Начать с шаблона">
                <button type="button" className={`template-card${templateId === "" ? " is-selected" : ""}`} onClick={() => setTemplateId("")} aria-pressed={templateId === ""}>
                  <b>С чистого листа</b>
                  <span>Название, форму и охват задаёте сами</span>
                </button>
                {templates.map((t) => (
                  <div key={t.id} className={`template-card${templateId === String(t.id) ? " is-selected" : ""}`}>
                    <button type="button" className="template-card__pick" onClick={() => applyTemplate(String(t.id))} aria-pressed={templateId === String(t.id)}>
                      <b>{t.name}</b>
                      <span>
                        {COLLECT_MODE_LABELS[t.collect_mode]}, {t.fields.length} {plural(t.fields.length, ["поле", "поля", "полей"])}
                      </span>
                    </button>
                    {t.can_manage && (
                      <button type="button" className="link-btn danger-link" onClick={() => deleteTemplate(t)} aria-label={`Удалить шаблон «${t.name}»`}>
                        Удалить
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
            <label className="form-field">
              Название
              <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Например, «Кружки дополнительного образования»" autoFocus />
            </label>
            <label className="form-field">
              Что нужно сделать и как
              <textarea rows={4} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Описание увидит куратор над формой ответа" />
            </label>
          </div>
        )}

        {step === 1 && (
          <div className="wizard__body">
            {afterTask ? (
              <>
                <p className="hint">Охват — те же группы, что у предыдущего шага.</p>
                <fieldset className="choice-cards">
                  <legend>Шаг откроется для группы</legend>
                  {[
                    ["accepted", "После приёмки предыдущего шага", "Группа увидит шаг, когда проверяющий примет предыдущий"],
                    ["submitted", "Сразу после сдачи предыдущего", "Не ждать проверки — открыть, как только группа отправила"],
                  ].map(([v, l, h]) => (
                    <label key={v} className={`choice-card${unlockOn === v ? " is-selected" : ""}`}>
                      <input type="radio" name="unlock" value={v} checked={unlockOn === v} onChange={() => setUnlockOn(v)} />
                      <b>{l}</b>
                      <span>{h}</span>
                    </label>
                  ))}
                </fieldset>
              </>
            ) : (
              <>
                <fieldset className="choice-cards">
                  <legend>Кому</legend>
                  {(
                    [
                      ["all", scopedToDepartment ? "Всё моё отделение" : "Весь колледж", "Все активные группы"],
                      ...(scopedToDepartment ? [] : [["departments", "Отделения", "Например, только «Диджитал»"]]),
                      ["courses", "Курсы", "Например, только первый курс"],
                      ["groups", "Отдельные группы", "Выбрать из списка с поиском"],
                    ] as [ScopeKind, string, string][]
                  ).map(([v, l, h]) => (
                    <label key={v} className={`choice-card${scopeKind === v ? " is-selected" : ""}`}>
                      <input type="radio" name="scope" value={v} checked={scopeKind === v} onChange={() => setScopeKind(v)} />
                      <b>{l}</b>
                      <span>{h}</span>
                    </label>
                  ))}
                </fieldset>
                {scopeKind === "departments" && (
                  <div className="inline-form">
                    {departments.map((d) => (
                      <label key={d.id}>
                        <input type="checkbox" checked={departmentIds.includes(d.id)} onChange={() => toggle(departmentIds, setDepartmentIds, d.id)} /> {d.name}
                      </label>
                    ))}
                  </div>
                )}
                {scopeKind === "courses" && (
                  <div className="inline-form">
                    {[1, 2, 3, 4].map((c) => (
                      <label key={c}>
                        <input type="checkbox" checked={courses.includes(c)} onChange={() => toggle(courses, setCourses, c)} /> {c} курс
                      </label>
                    ))}
                  </div>
                )}
                {scopeKind === "groups" && (
                  <FilterableMultiSelect
                    options={groups.map((g) => ({ value: String(g.id), label: `${g.code} (курс ${g.course})` }))}
                    selected={groupIds.map(String)}
                    onChange={(next) => setGroupIds(next.map(Number))}
                    size={8}
                    ariaLabel="Группы"
                  />
                )}
                <details className="wizard__details">
                  <summary>Исключить группы{excludeIds.length > 0 ? ` (${excludeIds.length})` : ""}</summary>
                  <FilterableMultiSelect
                    options={groups.map((g) => ({ value: String(g.id), label: g.code }))}
                    selected={excludeIds.map(String)}
                    onChange={(next) => setExcludeIds(next.map(Number))}
                    size={6}
                    ariaLabel="Исключить группы"
                  />
                </details>
                {preview && (
                  <div className="scope-count" role="status">
                    <span>
                      <b>{preview.groups}</b> {plural(preview.groups, ["группа", "группы", "групп"])}, {preview.students}{" "}
                      {plural(preview.students, ["студент", "студента", "студентов"])}, {preview.curators}{" "}
                      {plural(preview.curators, ["куратор", "куратора", "кураторов"])} получат задачу.
                    </span>
                    {preview.without_curator.length > 0 && (
                      <span className="scope-count__warn">
                        Без куратора: {preview.without_curator.join(", ")} — задача будет ждать, пока группе не назначат куратора.
                      </span>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {step === 2 && (
          <div className="wizard__body">
            <fieldset className="choice-cards">
              <legend>Как собирать ответ</legend>
              {Object.entries(COLLECT_MODE_LABELS).map(([v, l]) => (
                <label key={v} className={`choice-card${mode === v ? " is-selected" : ""}`}>
                  <input type="radio" name="mode" value={v} checked={mode === v} onChange={() => setMode(v)} />
                  <b>{l}</b>
                  <span>{MODE_HINTS[v]}</span>
                </label>
              ))}
            </fieldset>
            <ol className="field-cards" aria-label="Поля формы">
              {fields.map((f, i) => (
                <li key={i} className="field-card">
                  <div className="field-card__row">
                    <label className="form-field field-card__name">
                      Название поля {i + 1}
                      <input placeholder="Название поля" value={f.label} onChange={(e) => updateField(i, { label: e.target.value })} />
                    </label>
                    <label className="form-field">
                      Тип поля {i + 1}
                      <select value={f.type} onChange={(e) => changeType(i, e.target.value as TaskFieldType)}>
                        {Object.entries(FIELD_TYPE_LABELS).map(([v, l]) => (
                          <option key={v} value={v}>
                            {l}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  {(f.type === "select" || f.type === "multiselect") && (
                    <label className="form-field">
                      Варианты поля {i + 1}
                      <input
                        placeholder="Через запятую: спорт, танцы, хор"
                        value={f.optionsText}
                        onChange={(e) => updateField(i, { optionsText: e.target.value })}
                      />
                    </label>
                  )}
                  <div className="field-card__row field-card__row--meta">
                    {mode !== "group" && targets.length > 0 && (
                      <select
                        value={f.dossierField}
                        onChange={(e) => linkField(i, e.target.value)}
                        aria-label={`Записать в досье, поле ${i + 1}`}
                        title="После приёмки ответ запишется в это поле досье студента"
                      >
                        <option value="">В досье не записывать</option>
                        {targets.map((t) => (
                          <option key={t.key} value={t.key}>
                            В досье: {t.label}
                          </option>
                        ))}
                      </select>
                    )}
                    <label className="filter-check">
                      <input type="checkbox" checked={f.required} onChange={(e) => updateField(i, { required: e.target.checked })} /> Обязательное
                    </label>
                    <span className="field-card__tools">
                      <button type="button" className="icon-btn" onClick={() => move(i, -1)} disabled={i === 0} title="Выше" aria-label={`Поле ${i + 1} выше`}>
                        ↑
                      </button>
                      <button type="button" className="icon-btn" onClick={() => move(i, 1)} disabled={i === fields.length - 1} title="Ниже" aria-label={`Поле ${i + 1} ниже`}>
                        ↓
                      </button>
                      <button
                        type="button"
                        className="link-btn danger-link"
                        aria-label={`Убрать поле ${i + 1}`}
                        onClick={() => setFields((p) => p.filter((_, idx) => idx !== i))}
                        disabled={fields.length === 1}
                      >
                        Убрать
                      </button>
                    </span>
                  </div>
                </li>
              ))}
            </ol>
            <p>
              <button type="button" className="btn-secondary" onClick={() => setFields((p) => [...p, { ...EMPTY_FIELD }])} disabled={fields.length >= 30}>
                + Добавить поле
              </button>
            </p>
          </div>
        )}

        {step === 3 && (
          <div className="wizard__body">
            <label className="form-field">
              Срок
              <input type="date" value={dueDate} min={minDue} onChange={(e) => setDueDate(e.target.value)} />
            </label>
            <fieldset className="choice-cards">
              <legend>Кто проверяет</legend>
              {Object.entries(REVIEWER_LABELS).map(([v, l]) => (
                <label key={v} className={`choice-card${reviewer === v ? " is-selected" : ""}`}>
                  <input type="radio" name="reviewer" value={v} checked={reviewer === v} onChange={() => setReviewer(v)} />
                  <b>{l}</b>
                </label>
              ))}
            </fieldset>
            <div className="wizard__summary">
              <b>{title || "Без названия"}</b>
              <span>
                {COLLECT_MODE_LABELS[mode]}, {fields.length} {plural(fields.length, ["поле", "поля", "полей"])}
                {afterTask ? ", те же группы, что у предыдущего шага" : preview ? `, ${preview.groups} ${plural(preview.groups, ["группа", "группы", "групп"])}` : ""}
              </span>
            </div>
          </div>
        )}

        {error && (
          <div className="error-text" role="alert">
            {error}
          </div>
        )}

        <div className="wizard__nav">
          {step > 0 ? (
            <button type="button" className="btn-secondary" onClick={() => goTo((step - 1) as Step)}>
              Назад
            </button>
          ) : (
            <span />
          )}
          <button type="submit" className="btn-primary" disabled={busy}>
            {step < 3 ? `Дальше: ${STEPS[step + 1].toLowerCase()}` : "Создать и разослать"}
          </button>
        </div>
      </form>

      <aside className="wizard__preview" aria-label="Так увидит куратор">
        <h4>Так увидит куратор</h4>
        <div className="inbox-list wizard__preview-row">
          <div className="inbox-row">
            <span className="status-mark" aria-hidden="true">
              <svg viewBox="0 0 18 18" width="18" height="18">
                <circle cx="9" cy="9" r="7.5" fill="none" className="sm-stroke-idle" strokeWidth="2" />
              </svg>
            </span>
            <div className="inbox-row__main">
              <span className="inbox-row__title">{title || "Название задачи"}</span>
              <div className="inbox-row__meta">
                <span className="group-chip">СА172</span>
                <span>{COLLECT_MODE_LABELS[mode]}</span>
              </div>
            </div>
            <div className="inbox-row__due">
              <b>{dueDate ? relativeDue(dueDate) : "—"}</b>
              <span>{dueDate ? formatDueShort(dueDate) : ""}</span>
            </div>
          </div>
        </div>
        {description && <p className="wizard__preview-desc">{description}</p>}
        <div className="wizard__preview-answer">
          {mode !== "group" && <span className="answer-row__name">Алексеев Пётр</span>}
          {previewFields.length === 0 ? (
            <p className="hint">Здесь появятся поля формы.</p>
          ) : (
            previewFields.map((f) => (
              <div key={f.key} className="group-answer__field">
                <span className="group-answer__label">
                  {f.label}
                  {f.required && <span className="required-mark"> обязательно</span>}
                </span>
                <AnswerInput field={f} value={sample[f.key]} onChange={(v) => setSample((s) => ({ ...s, [f.key]: v }))} label={`Пример: ${f.label}`} />
              </div>
            ))
          )}
        </div>
      </aside>
    </div>
  );
}
