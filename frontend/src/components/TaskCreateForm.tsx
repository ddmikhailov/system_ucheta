import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { COLLECT_MODE_LABELS, FIELD_TYPE_LABELS, REVIEWER_LABELS } from "../constants/tasks";
import { todayIso } from "../utils/date";
import type { DepartmentAdmin, DossierTarget, StudyGroupAdmin, TaskDetail, TaskField, TaskFieldType, TaskTemplate } from "../api/types";
import { DEPARTMENT_SCOPED_ROLES, inRoles } from "../constants/roles";

type ScopeKind = "all" | "departments" | "courses" | "groups";

interface FieldDraft {
  label: string;
  type: TaskFieldType;
  required: boolean;
  optionsText: string;
  dossierField: string;
}

const EMPTY_FIELD: FieldDraft = { label: "", type: "text", required: false, optionsText: "", dossierField: "" };
const FUNDING_OPTIONS = "бюджет, договор";

// Создание задачи: описание → охват → режим сбора → форма ответа → срок и проверка.
export interface AfterTask {
  id: number;
  title: string;
  due_date: string;
}

// Режим «следующий шаг»: охват берётся у предыдущего шага, срок не раньше его срока, выбирается момент открытия.
export default function TaskCreateForm({ onCreated, afterTask }: { onCreated: (task: TaskDetail) => void; afterTask?: AfterTask | null }) {
  const { user } = useAuth();
  const scopedToDepartment = inRoles(user?.role, DEPARTMENT_SCOPED_ROLES);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [mode, setMode] = useState("student");
  const [reviewer, setReviewer] = useState("dept_head");
  const [dueDate, setDueDate] = useState(afterTask && afterTask.due_date > todayIso() ? afterTask.due_date : todayIso());
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

  async function deleteTemplate() {
    const t = templates.find((x) => String(x.id) === templateId);
    if (!t || !window.confirm(`Удалить шаблон «${t.name}»? Созданные по нему задачи не изменятся.`)) return;
    try {
      await api.delete(`/tasks/templates/${t.id}`);
      setTemplates((prev) => prev.filter((x) => x.id !== t.id));
      setTemplateId("");
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

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const payloadFields: TaskField[] = fields.map((f) => ({
      label: f.label,
      type: f.type,
      required: f.required,
      options: f.type === "select" || f.type === "multiselect" ? f.optionsText.split(",").map((o) => o.trim()).filter(Boolean) : [],
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
        scope: {
          all_groups: scopeKind === "all",
          department_ids: scopeKind === "departments" ? departmentIds : [],
          courses: scopeKind === "courses" ? courses : [],
          group_ids: scopeKind === "groups" ? groupIds : [],
          exclude_group_ids: excludeIds,
        },
      });
      onCreated(task);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось создать задачу");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="add-block" onSubmit={submit}>
      <p className="add-block__title">{afterTask ? `Следующий шаг после «${afterTask.title}»` : "Новая задача"}</p>
      {afterTask && (
        <div className="inline-form">
          <label>
            Шаг откроется для группы{" "}
            <select value={unlockOn} onChange={(e) => setUnlockOn(e.target.value)}>
              <option value="accepted">после того, как предыдущий шаг принят</option>
              <option value="submitted">сразу после того, как предыдущий шаг сдан</option>
            </select>
          </label>
        </div>
      )}
      {error && <div className="error-text">{error}</div>}

      {templates.length > 0 && !afterTask && (
        <div className="inline-form">
          <select value={templateId} onChange={(e) => applyTemplate(e.target.value)} aria-label="Шаблон">
            <option value="">Начать с пустой формы</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                Из шаблона: {t.name}
              </option>
            ))}
          </select>
          {templates.find((t) => String(t.id) === templateId)?.can_manage && (
            <button type="button" className="link-btn" onClick={deleteTemplate}>
              Удалить шаблон
            </button>
          )}
        </div>
      )}

      <div className="inline-form">
        <input placeholder="Название" value={title} onChange={(e) => setTitle(e.target.value)} required style={{ flex: 1, minWidth: 220 }} />
        <label>
          Срок{" "}
          <input type="date" value={dueDate} min={afterTask && afterTask.due_date > todayIso() ? afterTask.due_date : todayIso()} onChange={(e) => setDueDate(e.target.value)} required />
        </label>
      </div>
      <textarea
        placeholder="Описание: что нужно сделать и как"
        rows={3}
        style={{ width: "100%" }}
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />

      {afterTask ? (
        <p className="hint">Охват — те же группы, что у предыдущего шага.</p>
      ) : (
        <>
      <p className="add-block__title">Кому</p>
      <div className="inline-form">
        <select value={scopeKind} onChange={(e) => setScopeKind(e.target.value as ScopeKind)}>
          <option value="all">{scopedToDepartment ? "Всё моё отделение" : "Весь колледж"}</option>
          {!scopedToDepartment && <option value="departments">Выбранные отделения</option>}
          <option value="courses">Выбранные курсы</option>
          <option value="groups">Выбранные группы</option>
        </select>
      </div>
      {scopeKind === "departments" && (
        <div className="inline-form">
          {departments.map((d) => (
            <label key={d.id}>
              <input type="checkbox" checked={departmentIds.includes(d.id)} onChange={() => toggle(departmentIds, setDepartmentIds, d.id)} />{" "}
              {d.name}
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
        <select
          multiple
          size={8}
          style={{ width: "100%" }}
          value={groupIds.map(String)}
          onChange={(e) => setGroupIds(Array.from(e.target.selectedOptions, (o) => Number(o.value)))}
        >
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.code} (курс {g.course})
            </option>
          ))}
        </select>
      )}
      <details>
        <summary>Исключить группы</summary>
        <select
          multiple
          size={6}
          style={{ width: "100%" }}
          value={excludeIds.map(String)}
          onChange={(e) => setExcludeIds(Array.from(e.target.selectedOptions, (o) => Number(o.value)))}
        >
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.code}
            </option>
          ))}
        </select>
      </details>
        </>
      )}

      <p className="add-block__title">Как собирать ответ</p>
      <div className="inline-form">
        <select value={mode} onChange={(e) => setMode(e.target.value)}>
          {Object.entries(COLLECT_MODE_LABELS).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
        <label>
          Проверяет{" "}
          <select value={reviewer} onChange={(e) => setReviewer(e.target.value)}>
            {Object.entries(REVIEWER_LABELS).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="hint">
        {mode === "group" && "Один ответ от группы (видеовизитка, план работы)."}
        {mode === "student" && "Строка на каждого студента группы (кружки, согласия, справки). Поля можно связать с досье: форма откроется заполненной, а принятые ответы запишутся в карточки студентов."}
        {mode === "selected" && "Куратор сам отмечает, кого задача касается, и заполняет только их."}
      </p>

      <p className="add-block__title">Форма ответа</p>
      {fields.map((f, i) => (
        <div className="inline-form" key={i}>
          <input placeholder="Название поля" value={f.label} onChange={(e) => updateField(i, { label: e.target.value })} required />
          <select value={f.type} onChange={(e) => changeType(i, e.target.value as TaskFieldType)}>
            {Object.entries(FIELD_TYPE_LABELS).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
          {(f.type === "select" || f.type === "multiselect") && (
            <input
              placeholder="Варианты через запятую"
              value={f.optionsText}
              onChange={(e) => updateField(i, { optionsText: e.target.value })}
              required
            />
          )}
          {mode !== "group" && targets.length > 0 && (
            <select
              value={f.dossierField}
              onChange={(e) => linkField(i, e.target.value)}
              aria-label="Записать в досье"
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
          <label>
            <input type="checkbox" checked={f.required} onChange={(e) => updateField(i, { required: e.target.checked })} /> Обязательное
          </label>
          <button type="button" className="link-btn" onClick={() => move(i, -1)} disabled={i === 0} title="Выше" aria-label="Выше">
            ↑
          </button>
          <button type="button" className="link-btn" onClick={() => move(i, 1)} disabled={i === fields.length - 1} title="Ниже" aria-label="Ниже">
            ↓
          </button>
          <button type="button" className="link-btn" onClick={() => setFields((p) => p.filter((_, idx) => idx !== i))} disabled={fields.length === 1}>
            Убрать
          </button>
        </div>
      ))}
      <p>
        <button type="button" className="link-btn" onClick={() => setFields((p) => [...p, { ...EMPTY_FIELD }])} disabled={fields.length >= 30}>
          + Добавить поле
        </button>
      </p>

      <p>
        <button type="submit" disabled={busy}>
          Создать и разослать
        </button>
      </p>
    </form>
  );
}
