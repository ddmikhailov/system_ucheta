import type { MarkCodeOption } from "../api/types";

/** Ряд кнопок с кодами отметок вместо выпадающего списка — быстрее
 * проставлять посещаемость на каждый день, особенно с телефона. */
export default function MarkCodeButtons({
  value,
  markCodes,
  onChange,
}: {
  value: string | null;
  markCodes: MarkCodeOption[];
  onChange: (code: string | null) => void;
}) {
  return (
    <div className="mark-code-buttons">
      {/* «Присутствует» — зелёная галочка вместо буквы «Я»: читается сразу, без расшифровки. */}
      <button
        type="button"
        className={`mark-code-btn mark-code-btn--present ${value === null ? "active" : ""}`}
        onClick={() => onChange(null)}
        title="Присутствует"
        aria-label="Присутствует"
        aria-pressed={value === null}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {markCodes.map((m) => (
        <button
          key={m.code}
          type="button"
          className={`mark-code-btn ${value === m.code ? "active" : ""}`}
          onClick={() => onChange(m.code)}
          title={m.name}
          aria-pressed={value === m.code}
        >
          {m.code.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
