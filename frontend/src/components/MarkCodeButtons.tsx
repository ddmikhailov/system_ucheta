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
      <button
        type="button"
        className={`mark-code-btn ${value === null ? "active" : ""}`}
        onClick={() => onChange(null)}
        title="Присутствует"
      >
        Я
      </button>
      {markCodes.map((m) => (
        <button
          key={m.code}
          type="button"
          className={`mark-code-btn ${value === m.code ? "active" : ""}`}
          onClick={() => onChange(m.code)}
          title={m.name}
        >
          {m.code.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
