import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError, downloadFile } from "../api/client";
import { GROUP_LIST_FIELDS, GROUP_LIST_PRESETS } from "../constants/groupListFields";
import { useEscapeKey } from "../hooks/useEscapeKey";

const STORAGE_KEY = "kait20.groupList";
const DEFAULT_KEYS = ["full_name", "phone", "email"];

function savedChoice(): { keys: string[]; numbering: boolean } {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    const known = new Set(GROUP_LIST_FIELDS.map((f) => f.key));
    const keys = Array.isArray(raw?.keys) ? raw.keys.filter((k: unknown) => typeof k === "string" && known.has(k)) : [];
    if (keys.length > 0) return { keys, numbering: raw.numbering !== false };
  } catch {
    // нет доступа к хранилищу браузера или там мусор — берём значения по умолчанию
  }
  return { keys: DEFAULT_KEYS, numbering: true };
}

/** «Список группы» для печати: куратор отмечает столбцы (например, ФИО + телефон + e-mail) и скачивает Word-файл
 * с таблицей из этих столбцов. Последний выбор запоминается в браузере. */
export default function GroupListModal({ groupId, groupCode, onClose }: { groupId: number; groupCode: string; onClose: () => void }) {
  const initial = savedChoice();
  const [keys, setKeys] = useState<string[]>(initial.keys);
  const [numbering, setNumbering] = useState(initial.numbering);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  useEscapeKey(onClose);

  // Порядок столбцов в документе — как в этом списке, а не по очереди нажатий.
  const ordered = GROUP_LIST_FIELDS.filter((f) => keys.includes(f.key));
  const columns = ordered.length + (numbering ? 1 : 0);

  function toggle(key: string) {
    setDone(false);
    setKeys((current) => (current.includes(key) ? current.filter((k) => k !== key) : [...current, key]));
  }

  async function download(e: FormEvent) {
    e.preventDefault();
    if (ordered.length === 0) return;
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      const query = `fields=${ordered.map((f) => f.key).join(",")}&numbering=${numbering}${title.trim() ? `&title=${encodeURIComponent(title.trim())}` : ""}`;
      await downloadFile(`/curator/groups/${groupId}/roster-sheet?${query}`, `Список_${groupCode}.docx`);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ keys: ordered.map((f) => f.key), numbering }));
      } catch {
        // запомнить выбор не вышло — файл всё равно скачан
      }
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сформировать список");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal group-list-modal" role="dialog" aria-modal="true" aria-label="Список группы для печати" onClick={(e) => e.stopPropagation()} onSubmit={download}>
        <h3>Список группы {groupCode} для печати</h3>
        <p className="hint">Отметьте столбцы — получите файл Word с таблицей из них. Особые данные (здоровье, учёт) в список не входят.</p>

        <div className="toolbar" role="group" aria-label="Готовые наборы">
          {GROUP_LIST_PRESETS.map((p) => (
            <button
              key={p.label}
              type="button"
              className={`chip${p.keys.length === ordered.length && p.keys.every((k) => keys.includes(k)) ? " active" : ""}`}
              onClick={() => {
                setKeys(p.keys);
                setDone(false);
              }}
            >
              {p.label}
            </button>
          ))}
        </div>

        <fieldset className="group-list-fields">
          <legend>Столбцы</legend>
          {GROUP_LIST_FIELDS.map((f) => (
            <label key={f.key} title={f.hint}>
              <input type="checkbox" checked={keys.includes(f.key)} onChange={() => toggle(f.key)} /> {f.label}
              {f.hint ? <span className="hint"> — {f.hint}</span> : null}
            </label>
          ))}
        </fieldset>

        <label className="inline-check">
          <input type="checkbox" checked={numbering} onChange={(e) => setNumbering(e.target.checked)} /> Нумерация строк (столбец «№»)
        </label>
        <label>
          Заголовок (необязательно)
          <input value={title} maxLength={120} placeholder={`Список группы ${groupCode}`} onChange={(e) => setTitle(e.target.value)} />
        </label>

        <p className="hint" aria-live="polite">
          {ordered.length === 0 ? "Выберите хотя бы один столбец." : `В таблице столбцов: ${columns}. Ширина страницы подбирается сама.`}
        </p>
        {error && <div className="error-text">{error}</div>}
        {done && <p className="hint">Файл скачан. Откройте его в Word и распечатайте.</p>}

        <div className="actions">
          <button type="submit" disabled={busy || ordered.length === 0}>
            Скачать .docx
          </button>
          <button type="button" className="link-btn" onClick={onClose}>
            Закрыть
          </button>
        </div>
      </form>
    </div>
  );
}
