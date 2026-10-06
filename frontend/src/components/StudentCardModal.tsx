import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError, downloadFile } from "../api/client";
import { STUDENT_CARD_FIELDS, STUDENT_CARD_PRESETS } from "../constants/studentCardFields";
import { useEscapeKey } from "../hooks/useEscapeKey";

const STORAGE_KEY = "kait20.studentCard";
const DEFAULT_KEYS = STUDENT_CARD_FIELDS.map((f) => f.key);

function savedChoice(): { keys: string[]; blankSections: boolean } {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    const known = new Set(DEFAULT_KEYS);
    const keys = Array.isArray(raw?.keys) ? raw.keys.filter((k: unknown) => typeof k === "string" && known.has(k)) : [];
    if (keys.length > 0) return { keys, blankSections: raw.blankSections !== false };
  } catch {
    // нет доступа к хранилищу браузера или там мусор — берём значения по умолчанию
  }
  return { keys: DEFAULT_KEYS, blankSections: true };
}

/** «Личная карточка обучающегося» (Word, бланк колледжа): куратор отмечает поля, которые заполнить из платформы;
 * остальные остаются пустыми строками бланка. Для одного студента или для всей группы (каждая карточка с новой страницы).
 * `endpoint` — адрес без параметров: `/students/7/dossier/card` или `/curator/groups/3/cards`. */
export default function StudentCardModal({
  endpoint, heading, filename, onClose,
}: { endpoint: string; heading: string; filename: string; onClose: () => void }) {
  const initial = savedChoice();
  const [keys, setKeys] = useState<string[]>(initial.keys);
  const [blankSections, setBlankSections] = useState(initial.blankSections);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  useEscapeKey(onClose);

  const ordered = STUDENT_CARD_FIELDS.filter((f) => keys.includes(f.key));

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
      await downloadFile(`${endpoint}?fields=${ordered.map((f) => f.key).join(",")}&blank_sections=${blankSections}`, filename);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ keys: ordered.map((f) => f.key), blankSections }));
      } catch {
        // запомнить выбор не вышло — файл всё равно скачан
      }
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сформировать карточку");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal group-list-modal" role="dialog" aria-modal="true" aria-label="Личная карточка в Word" onClick={(e) => e.stopPropagation()} onSubmit={download}>
        <h3>{heading}</h3>
        <p className="hint">
          Отметьте, что заполнить из платформы, — остальное в бланке колледжа останется пустым для записи от руки. Особые
          данные (здоровье, учёт) в карточку не входят.
        </p>

        <div className="toolbar" role="group" aria-label="Готовые наборы">
          {STUDENT_CARD_PRESETS.map((p) => (
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
          <legend>Заполнить из платформы</legend>
          {STUDENT_CARD_FIELDS.map((f) => (
            <label key={f.key} title={f.hint}>
              <input type="checkbox" checked={keys.includes(f.key)} onChange={() => toggle(f.key)} /> {f.label}
              {f.hint ? <span className="hint"> — {f.hint}</span> : null}
            </label>
          ))}
        </fieldset>

        <label className="inline-check">
          <input type="checkbox" checked={blankSections} onChange={(e) => setBlankSections(e.target.checked)} /> Оставить разделы учебной части
          (оценки, практики, ГИА, взыскания) — для записи от руки
        </label>

        <p className="hint" aria-live="polite">
          {ordered.length === 0 ? "Выберите хотя бы одно поле." : "Данные студента, которых нет в досье, останутся пустыми строками."}
        </p>
        {error && <div className="error-text">{error}</div>}
        {done && <p className="hint">Файл скачан. Откройте его в Word, допишите от руки или распечатайте.</p>}

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
