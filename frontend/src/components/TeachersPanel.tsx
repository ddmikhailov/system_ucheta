import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type { GroupSubject, GroupSubjects } from "../api/types";
import { useEscapeKey } from "../hooks/useEscapeKey";
import { telHref } from "../utils/phone";
import { dialogs, toast } from "../utils/feedback";
import { filterByQuery } from "../utils/searchMatch";

interface Draft {
  code: string;
  name: string;
  teacher_name: string;
  teacher_phone: string;
  note: string;
}

const EMPTY: Draft = { code: "", name: "", teacher_name: "", teacher_phone: "", note: "" };

function toDraft(s: GroupSubject): Draft {
  return { code: s.code ?? "", name: s.name, teacher_name: s.teacher_name ?? "", teacher_phone: s.teacher_phone ?? "", note: s.note ?? "" };
}

/** Дисциплины группы и их преподаватели с телефонами (п. 5.1.5 положения о кураторе). Раздел «Успеваемость»:
 * куратору нужно быстро найти, кому позвонить по дисциплине. Ввод ручной; код дисциплины («МДК.01.01») нужен,
 * чтобы журнал дисциплины находил свою строку. Править может тот, кто ведёт группу; остальные только читают. */
export default function TeachersPanel({ groupId }: { groupId: number }) {
  const [data, setData] = useState<GroupSubjects | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<GroupSubject | "new" | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.get<GroupSubjects>(`/groups/${groupId}/subjects`));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось загрузить преподавателей");
    }
  }, [groupId]);

  useEffect(() => {
    // Загрузка при открытии вкладки: setState — после await внутри load().
    // oxlint-disable-next-line react/set-state-in-effect
    load();
  }, [load]);

  async function remove(subject: GroupSubject) {
    const ok = await dialogs.confirm(`Удалить дисциплину «${subject.name}» из списка группы?`, { confirmLabel: "Удалить", danger: true });
    if (!ok) return;
    try {
      await api.delete(`/groups/${groupId}/subjects/${subject.id}`);
      toast("Дисциплина удалена", "ok");
      await load();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Не удалось удалить", "error");
    }
  }

  if (error) return <div className="error-text">{error}</div>;
  if (!data) return <p className="hint">Загрузка…</p>;

  const shown = filterByQuery(data.subjects, query, (s) => `${s.code ?? ""} ${s.name} ${s.teacher_name ?? ""}`);

  return (
    <section className="teachers" aria-label="Дисциплины и преподаватели">
      <div className="teachers__bar">
        <input
          type="search"
          value={query}
          placeholder="Дисциплина или преподаватель"
          aria-label="Поиск по дисциплине или преподавателю"
          onChange={(e) => setQuery(e.target.value)}
        />
        {data.can_edit && (
          <button type="button" onClick={() => setEditing("new")}>
            Добавить дисциплину
          </button>
        )}
      </div>

      {data.subjects.length === 0 && (
        <p className="hint">
          {data.can_edit
            ? "Список пуст. Добавьте дисциплины группы и телефоны преподавателей — они будут под рукой, когда нужно выяснить пропуски или оценки."
            : "Куратор ещё не заполнил список дисциплин и преподавателей."}
        </p>
      )}
      {data.subjects.length > 0 && shown.length === 0 && <p className="hint">Ничего не найдено.</p>}

      <ul className="teachers__list">
        {shown.map((s) => {
          const tel = telHref(s.teacher_phone);
          return (
            <li key={s.id} className="teachers-card">
              <div className="teachers-card__head">
                <h4 className="teachers-card__name">{s.name}</h4>
                {s.code && <span className="teachers-card__code">{s.code}</span>}
              </div>
              <div className="teachers-card__teacher">{s.teacher_name ?? <span className="hint">Преподаватель не указан</span>}</div>
              {s.teacher_phone &&
                (tel ? (
                  <a className="teachers-card__phone" href={tel}>
                    {s.teacher_phone}
                  </a>
                ) : (
                  <span className="teachers-card__phone">{s.teacher_phone}</span>
                ))}
              {s.note && <p className="teachers-card__note">{s.note}</p>}
              {data.can_edit && (
                <div className="teachers-card__actions">
                  <button type="button" className="btn-secondary" onClick={() => setEditing(s)}>
                    Изменить
                  </button>
                  <button type="button" className="link-btn" onClick={() => remove(s)}>
                    Удалить
                  </button>
                </div>
              )}
            </li>
          );
        })}
      </ul>

      {editing && (
        <SubjectForm
          groupId={groupId}
          subject={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            toast("Сохранено", "ok");
            await load();
          }}
        />
      )}
    </section>
  );
}

function SubjectForm({ groupId, subject, onClose, onSaved }: { groupId: number; subject: GroupSubject | null; onClose: () => void; onSaved: () => void }) {
  const [draft, setDraft] = useState<Draft>(subject ? toDraft(subject) : EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEscapeKey(onClose);

  const set = (key: keyof Draft) => (e: { target: { value: string } }) => setDraft((d) => ({ ...d, [key]: e.target.value }));

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      code: draft.code.trim() || null,
      name: draft.name,
      teacher_name: draft.teacher_name.trim() || null,
      teacher_phone: draft.teacher_phone.trim() || null,
      note: draft.note.trim() || null,
    };
    try {
      if (subject) await api.put(`/groups/${groupId}/subjects/${subject.id}`, body);
      else await api.post(`/groups/${groupId}/subjects`, body);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal" role="dialog" aria-modal="true" aria-label="Дисциплина группы" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <h3>{subject ? "Дисциплина группы" : "Новая дисциплина"}</h3>
        <label>
          Название дисциплины
          <input value={draft.name} maxLength={255} required autoFocus onChange={set("name")} />
        </label>
        <label>
          Код дисциплины
          <input value={draft.code} maxLength={32} placeholder="МДК.01.01" onChange={set("code")} />
        </label>
        <label>
          Преподаватель
          <input value={draft.teacher_name} maxLength={255} placeholder="Фамилия И. О." onChange={set("teacher_name")} />
        </label>
        <label>
          Телефон преподавателя
          <input type="tel" value={draft.teacher_phone} maxLength={32} onChange={set("teacher_phone")} />
        </label>
        <label>
          Примечание
          <input value={draft.note} maxLength={500} placeholder="Например, когда лучше звонить" onChange={set("note")} />
        </label>
        {error && <div className="error-text">{error}</div>}
        <div className="actions">
          <button type="submit" disabled={busy || !draft.name.trim()}>
            Сохранить
          </button>
          <button type="button" className="link-btn" onClick={onClose}>
            Отмена
          </button>
        </div>
      </form>
    </div>
  );
}
