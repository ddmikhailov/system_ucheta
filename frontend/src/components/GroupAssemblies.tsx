import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError, downloadFile } from "../api/client";
import type { GroupAssemblies as GroupAssembliesData, GroupAssembly } from "../api/types";
import { useEscapeKey } from "../hooks/useEscapeKey";
import { formatDateRu } from "../utils/date";
import { dialogs } from "../utils/feedback";
import TextArea from "./TextArea";

/** Окно общего собрания группы: председатель, секретарь, повестка, «слушали / постановили». Из него делается протокол. */
function AssemblyForm({
  groupId, year, assembly, onSaved, onClose,
}: { groupId: number; year: string; assembly: GroupAssembly | null; onSaved: () => void; onClose: () => void }) {
  const [date, setDate] = useState(assembly?.assembly_date ?? "");
  const [number, setNumber] = useState(assembly ? String(assembly.number) : "");
  const [chair, setChair] = useState(assembly?.chair ?? "");
  const [secretary, setSecretary] = useState(assembly?.secretary ?? "");
  const [count, setCount] = useState(assembly?.present_count != null ? String(assembly.present_count) : "");
  const [agenda, setAgenda] = useState(assembly?.agenda ?? "");
  const [listened, setListened] = useState(assembly?.listened ?? "");
  const [resolved, setResolved] = useState(assembly?.resolved ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEscapeKey(onClose);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      assembly_date: date || null, number: number ? Number(number) : null, chair: chair || null, secretary: secretary || null,
      present_count: count === "" ? null : Number(count), agenda: agenda || null, listened: listened || null,
      resolved: resolved || null, ...(date ? {} : { school_year: year }),
    };
    try {
      if (assembly) await api.put(`/assemblies/${assembly.id}`, body);
      else await api.post(`/assemblies/groups/${groupId}`, body);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить собрание");
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal event-form" role="dialog" aria-modal="true" aria-label="Общее собрание группы" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <h3>{assembly ? `Общее собрание группы №${assembly.number}` : "Новое общее собрание группы"}</h3>
        <div className="inline-form form-fields">
          <label>
            Дата проведения
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <label>
            Номер собрания
            <input type="number" min={1} max={99} value={number} placeholder="следующий" onChange={(e) => setNumber(e.target.value)} />
          </label>
        </div>
        <div className="inline-form form-fields">
          <label>
            Председатель
            <input type="text" maxLength={255} value={chair} onChange={(e) => setChair(e.target.value)} />
          </label>
          <label>
            Секретарь
            <input type="text" maxLength={255} value={secretary} onChange={(e) => setSecretary(e.target.value)} />
          </label>
        </div>
        <label>
          Студентов присутствовало (число)
          <input type="number" min={0} max={500} value={count} onChange={(e) => setCount(e.target.value)} />
        </label>
        <label>
          Повестка (по одному вопросу в строке)
          <TextArea expandTitle="Повестка" rows={3} value={agenda} maxLength={3000} onChange={(e) => setAgenda(e.target.value)} />
        </label>
        <label>
          Слушали
          <TextArea expandTitle="Слушали" rows={3} value={listened} maxLength={5000} onChange={(e) => setListened(e.target.value)} />
        </label>
        <label>
          Постановили
          <TextArea expandTitle="Постановили" rows={3} value={resolved} maxLength={5000} onChange={(e) => setResolved(e.target.value)} />
        </label>
        {error && <div className="error-text">{error}</div>}
        <div className="actions">
          <button type="submit" disabled={busy}>
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

/** Протоколы общих собраний группы (п. 5.1.10) внутри «Папки куратора»: список с выгрузкой, правкой и удалением,
 * кнопка «Добавить протокол». Поимённой явки нет — только число присутствовавших. */
export default function GroupAssemblies({ groupId, year, onChanged }: { groupId: number; year: string; onChanged: () => void }) {
  const [data, setData] = useState<GroupAssembliesData | null>(null);
  const [form, setForm] = useState<{ assembly: GroupAssembly | null } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .get<GroupAssembliesData>(`/assemblies/groups/${groupId}?year=${year}`)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить собрания группы"));
  }, [groupId, year]);

  useEffect(load, [load]);

  function changed() {
    setForm(null);
    load();
    onChanged();
  }

  async function remove(a: GroupAssembly) {
    if (!(await dialogs.confirm(`Удалить общее собрание группы №${a.number}?`, { confirmLabel: "Удалить", danger: true }))) return;
    try {
      await api.delete(`/assemblies/${a.id}`);
      changed();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось удалить собрание");
    }
  }

  function download(a: GroupAssembly) {
    downloadFile(`/assemblies/${a.id}/protocol.docx`, `Протокол_общего_собрания_${a.number}.docx`).catch((err) =>
      setError(err instanceof ApiError ? err.message : "Не удалось скачать протокол"),
    );
  }

  return (
    <div className="folder-assemblies">
      {error && <div className="error-text">{error}</div>}
      {data?.assemblies.map((a) => (
        <div key={a.id} className="folder-assemblies__row">
          <span className="folder-assemblies__name">
            № {a.number}
            {a.assembly_date ? ` от ${formatDateRu(a.assembly_date)}` : ""}
          </span>
          <button type="button" className="btn-secondary" onClick={() => download(a)}>
            Скачать
          </button>
          <button type="button" className="link-btn" onClick={() => setForm({ assembly: a })}>
            Изменить
          </button>
          <button type="button" className="link-btn" onClick={() => remove(a)}>
            Удалить
          </button>
        </div>
      ))}
      <button type="button" className="btn-secondary" onClick={() => setForm({ assembly: null })}>
        Добавить протокол собрания
      </button>
      {form && <AssemblyForm groupId={groupId} year={year} assembly={form.assembly} onSaved={changed} onClose={() => setForm(null)} />}
    </div>
  );
}
