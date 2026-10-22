import { useState } from "react";
import type { ReactNode } from "react";

// Поле с видимой подписью сверху и необязательной подсказкой снизу: подпись всегда над полем, одной ширины с ним,
// поэтому ряды не «скачут»; плейсхолдер — только пример ввода.
export function Field({ label, hint, wide, children }: { label: string; hint?: string; wide?: boolean; children: ReactNode }) {
  return (
    <label className={`dossier-field${wide ? " dossier-field--wide" : ""}`}>
      <span className="dossier-field__label">{label}</span>
      {children}
      {hint && <span className="dossier-field__hint">{hint}</span>}
    </label>
  );
}

/** Значение для режима просмотра: пустое — приглушённое «не указано», а не пустая строка. */
export function Info({ label, value, wide }: { label: string; value: ReactNode; wide?: boolean }) {
  const empty = value === null || value === undefined || value === "";
  return (
    <div className={`info-item${wide ? " info-item--wide" : ""}`}>
      <dt>{label}</dt>
      <dd className={empty ? "info-empty" : undefined}>{empty ? "не указано" : value}</dd>
    </div>
  );
}

/** Раздел досье с двумя режимами. Сведения заполняются один раз и меняются редко: если в разделе уже что-то
 * есть, он показывается готовой информацией с кнопкой «Редактировать»; пустой раздел сразу открыт для ввода. */
export function DossierBlock({
  title,
  subtitle,
  filled,
  isPrivate,
  view,
  children,
}: {
  title: string;
  subtitle?: string;
  /** Есть ли в разделе сохранённые данные — тогда по умолчанию просмотр. */
  filled: boolean;
  isPrivate?: boolean;
  view: ReactNode;
  children: ReactNode;
}) {
  const [editing, setEditing] = useState(!filled);
  return (
    <section className={`dossier-section${isPrivate ? " dossier-section--private" : ""}${editing ? " is-editing" : ""}`}>
      <header className="dossier-section__head dossier-section__head--row">
        <div>
          <h4>{title}</h4>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {filled &&
          (editing ? (
            <button type="button" className="link-btn" onClick={() => setEditing(false)}>
              Свернуть
            </button>
          ) : (
            <button type="button" className="btn-secondary" onClick={() => setEditing(true)} aria-label={`Редактировать: ${title}`}>
              Редактировать
            </button>
          ))}
      </header>
      {editing ? children : view}
    </section>
  );
}
